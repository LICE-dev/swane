from multiprocessing import cpu_count

from nipype import Node, MapNode
from nipype.interfaces.fsl import (
    BET,
    FLIRT,
    FNIRT,
    InvWarp,
    ConvertXFM,
    ApplyWarp,
    ApplyXFM,
)

from swane.config.config_enums import CoreLimit, RegistrationEngine
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SynthMorphApply import SynthMorphApply
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from swane.nipype_pipeline.nodes.SynthMorphReg import SynthMorphReg
from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration
from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms
from swane.nipype_pipeline.nodes.ram_estimators import *
from swane.utils.ResourceManager import ResourceManager
from nipype.utils.filemanip import fname_presuffix

# FSL FLIRT cost -> antspyx affine metric. antspyx has no "MI"/"mutualinfo"
# literal: Mattes mutual information ("mattes") is its information-theoretic,
# cross-modality metric and is the closest analogue of FSL's mutualinfo/corratio
# costs (both used here for potentially cross-modality alignment). Intensity
# correlation costs map to ANTs global correlation ("GC"), least-squares to
# "meansquares". Anything unmapped falls back to the robust "mattes".
_ANTS_AFF_METRIC_BY_FLIRT_COST = {
    "mutualinfo": "mattes",
    "corratio": "mattes",
    "normmi": "mattes",
    "normcorr": "GC",
    "leastsq": "meansquares",
}


def resolve_registration_engine(
    synth_config, allow_ants: bool = True
) -> RegistrationEngine:
    """
    Resolve the configured registration engine from a Synth-tools config section.

    ``allow_ants=False`` keeps a workflow that has not yet been ported to the
    ANTs ordered-transform-list format on FSL when the (default) engine is ANTS,
    preserving that workflow's Phase-1 behaviour. SYNTH and FSL are honoured
    either way. Only ``linear_reg_workflow``/``nonlinear_reg_workflow`` pass
    ``allow_ants=True``; every other caller passes ``allow_ants=False`` until
    its own phase ports it.
    """
    engine = synth_config.getenum_safe("engine")
    if not allow_ants and engine == RegistrationEngine.ANTS:
        return RegistrationEngine.FSL
    return engine


def getn(result_list, index):
    """
    Extracts an element from a list for a single input of a Node (eg. aparcaseg from reconAll).

    """

    return result_list[index]


def get_tool_cpu_config(
    max_cpu: int,
    multicore_node_limit: CoreLimit,
    limit_synth_cores: bool,
) -> tuple[int, bool]:
    """
    Computes the thread count for a CPU-bound tool node (SynthStrip,
    SynthMorphReg, SynthSeg, AntsRegistration) and whether nipype's own
    scheduler must be made aware of it.

    Hard cap: the tool uses `threads` cores and nipype's resource accounting
    (node.n_procs) knows and reserves the same amount. Soft cap: the tool
    still uses `threads` cores.

    """
    if limit_synth_cores:
        cores = ResourceManager.SYNTH_CORE_LIMIT
        if max_cpu > 0:
            cores = min(cores, max_cpu)
        return cores, True

    if multicore_node_limit == CoreLimit.NO_LIMIT:
        return cpu_count(), False
    if multicore_node_limit == CoreLimit.HARD_CAP:
        return max_cpu, True
    # SOFT_CAP
    return max_cpu, False


def apply_tool_num_threads(
    node: Node,
    threads: int,
    hard: bool,
    soft_env_vars: tuple[str, ...] = (),
) -> None:
    """
    Applies a CPU-bound tool's thread count.

    Hard cap (or when the tool exposes no way to hide its thread usage from
    nipype, e.g. SynthSeg, or the ANTs node whose only thread knob is the
    ``num_threads`` input): sets the node's `num_threads` input, which nipype's
    scheduler reads back as node.n_procs -- a real, visible reservation. (For
    the ANTs node that input is what the node exports as
    ``ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS`` at run time; nipype couples
    ``num_threads`` to ``n_procs``, so such a tool can never truly hide its
    thread usage and is always scheduled as a real reservation.)

    Soft cap: leaves `num_threads` undefined (n_procs stays at its unaware
    default of 1) and instead sets the tool-specific environment variables that
    actually drive its thread count (SynthStrip's ``OMP_NUM_THREADS``,
    SynthMorph's ``TF_NUM_*``), invisible to nipype.

    """
    if hard or not soft_env_vars:
        node.inputs.num_threads = threads
        node.n_procs = threads
    else:
        node.inputs.environ = {
            **node.inputs.environ,
            **{var: str(threads) for var in soft_env_vars},
        }


# Backwards-compatible aliases: these helpers were named after Synth tools when
# they only served Synth nodes; freesurfer_workflow still imports them by name.
get_synth_cpu_config = get_tool_cpu_config
apply_synth_num_threads = apply_tool_num_threads


def get_deskull_node(
    name: str,
    use_synth: bool,
    mask: bool = False,
    bet_thr: float = None,
    bet_bias_correction: bool = False,
    bet_robust: bool = False,
    bet_threshold: bool = False,
    bet_surfaces: bool = False,
    synth_exclude_csf: bool = False,
    out_file: str = None,
    name_prefix: str = "",
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    limit_synth_cores: bool = False,
) -> Node:
    if use_synth:
        deskull_node = Node(SynthStrip(), name=name + "_synthstrip", mem_gb=5)
        if mask:
            mask_name = "brain_mask.nii.gz"
            if out_file:
                mask_name = fname_presuffix(out_file, suffix="_brain", use_ext=True)
            deskull_node.inputs.mask_file = mask_name
        deskull_node.inputs.exclude_csf = synth_exclude_csf
        threads, hard = get_tool_cpu_config(
            max_cpu, multicore_node_limit, limit_synth_cores
        )
        apply_tool_num_threads(
            deskull_node, threads, hard, soft_env_vars=("OMP_NUM_THREADS",)
        )
        if bet_surfaces:
            deskull_node.inskull_out_name = "mask_file"
    else:
        deskull_node = Node(BET(), name=name + "_bet")
        deskull_node.inputs.mask = mask
        deskull_node.inputs.threshold = bet_threshold
        if bet_thr is not None:
            deskull_node.inputs.frac = bet_thr
        if bet_bias_correction:
            deskull_node.inputs.reduce_bias = True
        elif bet_surfaces:
            deskull_node.inputs.surfaces = True
            deskull_node.inskull_out_name = "inskull_mask_file"
        elif bet_robust:
            deskull_node.inputs.robust = True

    deskull_node.long_name = name_prefix + " %s"
    if out_file:
        deskull_node.inputs.out_file = out_file

    return deskull_node


class RegistrationNodeWrapper:
    """Backend-neutral handle on a registration node and its transform outputs.

    ``warp``/``inv_warp`` keep the single-file view used by the FSL/Synth code
    paths (a FLIRT ``.mat``, an FNIRT/SynthMorph warp). ``fwd_transforms``/
    ``inv_transforms`` are the ordered-list view every backend exposes as a list
    of ``(node, field)`` sources; for FSL/Synth that list is the one single-file
    source, for ANTs it is the node's ``fwd_transforms``/``inv_transforms`` list
    outputs (already in ANTs right-to-left order).

    ``fwd_which_to_invert``/``inv_which_to_invert`` are the ``(node, field)``
    sources of the per-transform invert flags that ``AntsApplyTransforms``
    needs; they are ``None`` for FSL/Synth (which never invert on apply).
    """

    def __init__(
        self,
        input_node: Node,
        out_registered_node: Node,
        warp: str,
        inv_warp_node: Node,
        inv_warp: str,
        engine: RegistrationEngine = RegistrationEngine.FSL,
        fwd_transforms: list = None,
        inv_transforms: list = None,
        fwd_which_to_invert=None,
        inv_which_to_invert=None,
    ):
        self.input_node = input_node
        self.out_registered_node = out_registered_node
        self.warp = warp
        self.inv_warp_node = inv_warp_node
        self.inv_warp = inv_warp
        self.engine = engine
        self.fwd_transforms = fwd_transforms if fwd_transforms is not None else []
        self.inv_transforms = inv_transforms if inv_transforms is not None else []
        self.fwd_which_to_invert = fwd_which_to_invert
        self.inv_which_to_invert = inv_which_to_invert


def get_registration_node(
    name: str,
    engine: RegistrationEngine,
    workflow: CustomWorkflow,
    moving: str | list[Node | str],
    reference: str | list[Node | str],
    moving_brain: str | list[Node | str] = None,
    reference_brain: str | list[Node | str] = None,
    non_linear: bool = False,
    inverse: bool = False,
    is_volumetric: bool = True,
    flirt_cost: str = "mutualinfo",
    flirt_search: int = 90,
    name_prefix: str = "",
    name_suffix: str = "",
    test_run: bool = False,
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    limit_synth_cores: bool = False,
) -> RegistrationNodeWrapper:

    # Sometimes we want to use flirt on unbetted images to take advantage of skull for registration
    if moving_brain is None:
        moving_brain = moving

    if reference_brain is None:
        reference_brain = reference

    if engine == RegistrationEngine.SYNTH:
        # Prepare node inputs value
        if non_linear:
            mem_gb = 13
            model = "joint"
        else:
            mem_gb = 9
            model = "rigid"

        # test_run only cuts the *nonlinear* SynthMorph work (steps=5 below), so
        # only the joint node genuinely needs less RAM. Scale its reservation to
        # match the lowered gate (capabilities._probe_synth_ram), or the plugin's
        # prerun check would abort the pass on a host sized for the reduced gate.
        if test_run and non_linear:
            mem_gb *= ResourceManager.TEST_RUN_SYNTH_RAM_FACTOR

        synth_morph_reg = Node(
            SynthMorphReg(), name=name + "_synthmorphreg", mem_gb=mem_gb
        )
        synth_morph_reg.long_name = name_prefix + " %s " + name_suffix
        synth_morph_reg.inputs.model = model
        threads, hard = get_tool_cpu_config(
            max_cpu, multicore_node_limit, limit_synth_cores
        )
        apply_tool_num_threads(
            synth_morph_reg,
            threads,
            hard,
            soft_env_vars=("TF_NUM_INTRAOP_THREADS", "TF_NUM_INTEROP_THREADS"),
        )
        if test_run and non_linear:
            # Reduce deformable integration steps (default 7) for prerelease
            # test runs. FreeSurfer advises not to go below 5.
            synth_morph_reg.inputs.steps = 5
        if type(moving) == str:
            synth_morph_reg.inputs.in_file = moving
        else:
            workflow.connect(moving[0], moving[1], synth_morph_reg, "in_file")
        if type(reference) == str:
            synth_morph_reg.inputs.reference = reference
        else:
            workflow.connect(reference[0], reference[1], synth_morph_reg, "reference")

        return RegistrationNodeWrapper(
            input_node=synth_morph_reg,
            out_registered_node=synth_morph_reg,
            warp="warp_file",
            inv_warp_node=synth_morph_reg,
            inv_warp="inv_warp_file",
            engine=RegistrationEngine.SYNTH,
            fwd_transforms=[(synth_morph_reg, "warp_file")],
            inv_transforms=[(synth_morph_reg, "inv_warp_file")],
        )

    elif engine == RegistrationEngine.ANTS:
        # antspyx runs the affine and (for SyN) deformable stages in one node.
        # transform_type mirrors the FSL dof intent so the ANTs graph aligns
        # with what FLIRT/FNIRT expressed: dof=6 (rigid) for the volumetric
        # linear step, FLIRT's default dof=12 (affine) for the 2D linear step,
        # and SyN for the deformable step. The registration runs on the brain
        # images (moving_brain/reference_brain), exactly as FSL's affine stage
        # does; the resulting transform list is then applied to the whole-head
        # image downstream.
        if non_linear:
            transform_type = "SyN"
        elif is_volumetric:
            transform_type = "Rigid"
        else:
            transform_type = "Affine"

        ants_reg = Node(
            AntsRegistration(),
            name=name + "_antsreg",
            mem_gb=ResourceManager.ants_ram_requirements(),
        )
        ants_reg.long_name = name_prefix + " %s " + name_suffix
        ants_reg.inputs.transform_type = transform_type
        ants_reg.inputs.aff_metric = _ANTS_AFF_METRIC_BY_FLIRT_COST.get(
            flirt_cost, "mattes"
        )
        # antspyx has no correlation-ratio SyN metric; "mattes" (Mattes MI) is
        # the cross-modality-safe choice for the deformable stage too.
        if non_linear:
            ants_reg.inputs.syn_metric = "mattes"
        # ANTs takes its thread count only through num_threads (which the node
        # exports as the ITK env var); nipype couples that to n_procs, so there
        # is no soft-env-var path -- always a real, nipype-aware reservation.
        threads, hard = get_tool_cpu_config(
            max_cpu, multicore_node_limit, limit_synth_cores
        )
        apply_tool_num_threads(ants_reg, threads, hard)

        if type(moving_brain) == str:
            ants_reg.inputs.moving = moving_brain
        else:
            workflow.connect(moving_brain[0], moving_brain[1], ants_reg, "moving")
        if type(reference_brain) == str:
            ants_reg.inputs.fixed = reference_brain
        else:
            workflow.connect(reference_brain[0], reference_brain[1], ants_reg, "fixed")

        return RegistrationNodeWrapper(
            input_node=ants_reg,
            out_registered_node=ants_reg,
            # The single-file view carries the whole ordered list; the field
            # name contract (out_matrix_file/fieldcoeff_file) is preserved by
            # the workflow, its content is now an ANTs transform list.
            warp="fwd_transforms",
            inv_warp_node=ants_reg,
            inv_warp="inv_transforms",
            engine=RegistrationEngine.ANTS,
            fwd_transforms=[(ants_reg, "fwd_transforms")],
            inv_transforms=[(ants_reg, "inv_transforms")],
            fwd_which_to_invert=(ants_reg, "fwd_which_to_invert"),
            inv_which_to_invert=(ants_reg, "inv_which_to_invert"),
        )

    else:
        if non_linear:
            flirt = Node(FLIRT(), name=name + "_flirt")
            flirt.long_name = name_prefix + " %s " + name_suffix
            flirt.ram_estimator = FlirtRamEstimator()
            flirt.inputs.searchr_x = [-flirt_search, flirt_search]
            flirt.inputs.searchr_y = [-flirt_search, flirt_search]
            flirt.inputs.searchr_z = [-flirt_search, flirt_search]
            flirt.inputs.dof = 12
            # TODO consider switch to same-modality cost function
            flirt.inputs.cost = flirt_cost
            if type(moving_brain) == str:
                flirt.inputs.in_file = moving_brain
            else:
                workflow.connect(moving_brain[0], moving_brain[1], flirt, "in_file")
            if type(reference_brain) == str:
                flirt.inputs.reference = reference_brain
            else:
                workflow.connect(
                    reference_brain[0], reference_brain[1], flirt, "reference"
                )

            fnirt = Node(FNIRT(), name=name + "_fnirt")
            fnirt.long_name = name_prefix + " %s " + name_suffix
            fnirt.ram_estimator = FnirtRamEstimator()
            fnirt.inputs.fieldcoeff_file = True
            if test_run:
                # Speed up prerelease test runs by keeping FNIRT's default
                # 4-level pyramid but never descending to full resolution
                # (subsamp 1) and doing fewer iterations at the finer levels.
                # Dropping levels (2-element lists) is NOT safe: FNIRT keeps
                # --lambda/--estint/--applyinmask/--applyrefmask at their
                # 4-level internal defaults, and any mismatch in per-level list
                # lengths makes it abort (it prints usage and writes no warp).
                # Staying at length 4 keeps every internal default consistent.
                # Coarsest-first schedule stopping at subsamp 2 (never full
                # resolution): measured on the phantom this is the fastest of the
                # length-4 schemes tried and still clears the nonlinear target
                # alignment check with margin (Dice 0.94, NCC 0.79 vs 0.85/0.5).
                fnirt.inputs.subsampling_scheme = [4, 4, 4, 2]
                fnirt.inputs.max_nonlin_iter = [5, 5, 5, 3]
            workflow.connect(flirt, "out_matrix_file", fnirt, "affine_file")
            if type(moving) == str:
                fnirt.inputs.in_file = moving
            else:
                workflow.connect(moving[0], moving[1], fnirt, "in_file")
            if type(reference) == str:
                fnirt.inputs.ref_file = reference
            else:
                workflow.connect(reference[0], reference[1], fnirt, "ref_file")

            inv_warp = None
            if inverse:
                inv_warp = Node(InvWarp(), name=name + "_invwarp")
                inv_warp.ram_estimator = InvWarpRamEstimator()
                # No test_run speedup here: nipype's InvWarp interface defines
                # a `niter` trait (--niter=%d), but the actual FSL `invwarp`
                # binary has no such option ("Option doesn't exist!") -- it
                # takes no iteration-count argument at all. Setting it always
                # crashed the node; there is no real accuracy/speed knob to
                # cut on this tool.
                workflow.connect(fnirt, "fieldcoeff_file", inv_warp, "warp")
                if type(moving) == str:
                    inv_warp.inputs.ref_file = moving
                else:
                    workflow.connect(moving[0], moving[1], inv_warp, "reference")

            return RegistrationNodeWrapper(
                input_node=flirt,
                out_registered_node=fnirt,
                warp="fieldcoeff_file",
                inv_warp_node=inv_warp,
                inv_warp="inverse_warp",
                engine=RegistrationEngine.FSL,
                fwd_transforms=[(fnirt, "fieldcoeff_file")],
                inv_transforms=(
                    [(inv_warp, "inverse_warp")] if inv_warp is not None else []
                ),
            )
        else:
            flirt = Node(FLIRT(), name=name + "_flirt")
            flirt.long_name = name_prefix + " %s " + name_suffix
            flirt.ram_estimator = FlirtRamEstimator()
            if is_volumetric:
                flirt.inputs.cost = flirt_cost
                flirt.inputs.searchr_x = [-flirt_search, flirt_search]
                flirt.inputs.searchr_y = [-flirt_search, flirt_search]
                flirt.inputs.searchr_z = [-flirt_search, flirt_search]
                flirt.inputs.dof = 6
                flirt.inputs.interp = "trilinear"
            if type(moving_brain) == str:
                flirt.inputs.in_file = moving_brain
            else:
                workflow.connect(moving_brain[0], moving_brain[1], flirt, "in_file")
            if type(reference_brain) == str:
                flirt.inputs.reference = reference_brain
            else:
                workflow.connect(
                    reference_brain[0], reference_brain[1], flirt, "reference"
                )

            inv_xfm = None
            if inverse:
                inv_xfm = Node(ConvertXFM(), name=name + "_invwarp")
                inv_xfm.inputs.invert_xfm = True
                workflow.connect(flirt, "out_matrix_file", inv_xfm, "in_file")

            return RegistrationNodeWrapper(
                input_node=flirt,
                out_registered_node=flirt,
                warp="out_matrix_file",
                inv_warp_node=inv_xfm,
                inv_warp="out_file",
                engine=RegistrationEngine.FSL,
                fwd_transforms=[(flirt, "out_matrix_file")],
                inv_transforms=([(inv_xfm, "out_file")] if inv_xfm is not None else []),
            )


def apply_registration_node(
    name: str,
    use_synth: bool,
    workflow: CustomWorkflow,
    warp: list[Node | str],
    moving: str | list[Node | str],
    reference: str | list[Node | str],
    out_file: str | list[Node | str | tuple] = None,
    non_linear: bool = False,
    labelmap: bool = False,
    name_prefix: str = "",
    name_suffix: str = "",
    iterfield: list[str] = None,
) -> Node:
    node_class = Node if iterfield is None else MapNode
    node_kwargs = {} if iterfield is None else {"iterfield": iterfield}

    if use_synth:
        apply_node = node_class(
            SynthMorphApply(), name=name + "_morph_apply", **node_kwargs
        )
        apply_node.long_name = name_prefix + " %s " + name_suffix
        if labelmap:
            apply_node.inputs.method = "nearest"
        workflow.connect(warp[0], warp[1], apply_node, "warp_file")

    elif non_linear:
        apply_node = node_class(ApplyWarp(), name=name + "_apply_warp", **node_kwargs)
        apply_node.long_name = name_prefix + " %s " + name_suffix
        if labelmap:
            apply_node.inputs.interp = "nn"
        workflow.connect(warp[0], warp[1], apply_node, "field_file")
        if type(reference) == str:
            apply_node.inputs.ref_file = reference
        else:
            workflow.connect(reference[0], reference[1], apply_node, "ref_file")
    else:
        apply_node = node_class(ApplyXFM(), name=name + "_apply_xfm", **node_kwargs)
        apply_node.long_name = name_prefix + " %s " + name_suffix
        if labelmap:
            apply_node.inputs.interp = "nearestneighbour"
        workflow.connect(warp[0], warp[1], apply_node, "in_matrix_file")
        if type(reference) == str:
            apply_node.inputs.reference = reference
        else:
            workflow.connect(reference[0], reference[1], apply_node, "reference")

    if out_file:
        if type(out_file) == str:
            apply_node.inputs.out_file = out_file
        else:
            workflow.connect(out_file[0], out_file[1], apply_node, "out_file")
    if moving is None:
        pass
    elif type(moving) == str:
        apply_node.inputs.in_file = moving
    else:
        workflow.connect(moving[0], moving[1], apply_node, "in_file")

    return apply_node
