from multiprocessing import cpu_count

from nipype import Node, MapNode
from nipype.interfaces.utility import Merge
from nipype.interfaces.fsl import (
    BET,
    FLIRT,
    FNIRT,
    InvWarp,
    ConvertXFM,
    ApplyWarp,
    ApplyXFM,
)

from swane.config.config_enums import (
    CoreLimit,
    RegistrationEngine,
    DeskullEngine,
    DeskullModality,
)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SynthMorphApply import SynthMorphApply
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from swane.nipype_pipeline.nodes.SynthMorphReg import SynthMorphReg
from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration
from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
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


def resolve_deskull_engine(
    synth_config, allow_synthstrip: bool = True
) -> DeskullEngine:
    """
    Resolve the configured brain-extraction engine.

    ``allow_synthstrip=False`` keeps a workflow that must avoid FreeSurfer Synth
    tools (fMRI_preproc, mirroring its SynthMorph exclusion) off SYNTHSTRIP: when
    the configured engine is SYNTHSTRIP it falls back to the default ANTSPYNET.
    ANTSPYNET and BET are honoured either way.
    """
    engine = synth_config.getenum_safe("deskull_engine")
    if not allow_synthstrip and engine == DeskullEngine.SYNTHSTRIP:
        return DeskullEngine.ANTSPYNET
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
    max_cpu: int = 0,
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

    ``max_cpu`` bounds the *nipype-aware* branch only. ``CoreLimit.NO_LIMIT``
    makes ``get_tool_cpu_config`` answer ``cpu_count()`` with ``hard=False`` --
    "use every core, keep nipype unaware". A tool with no soft env-var knob
    cannot honour the second half: it lands here and would reserve
    ``cpu_count()`` procs. Where that exceeds the cores the subject allocated,
    ``MultiProc._prerun_check`` refuses the whole workflow ("Insufficient
    resources available for job") before a single node runs, so the reservation
    is clamped to the budget. A genuine hard cap is already within it, which
    makes this a no-op there.

    """
    if hard or not soft_env_vars:
        if max_cpu > 0:
            threads = min(threads, max_cpu)
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
    deskull_engine: DeskullEngine,
    mask: bool = False,
    bet_thr: float = None,
    antspynet_thr: float = None,
    bet_bias_correction: bool = False,
    bet_robust: bool = False,
    bet_threshold: bool = False,
    bet_surfaces: bool = False,
    synth_exclude_csf: bool = False,
    deskull_modality: DeskullModality = None,
    out_file: str = None,
    name_prefix: str = "",
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    limit_synth_cores: bool = False,
) -> Node:
    if deskull_engine == DeskullEngine.ANTSPYNET:
        deskull_node = Node(
            AntsPyNetBrainExtraction(),
            name=name + "_antspynet",
            mem_gb=ResourceManager.antspynet_ram_requirements(),
        )
        if deskull_modality is not None:
            deskull_node.inputs.modality = deskull_modality.value
        if antspynet_thr is not None:
            deskull_node.inputs.threshold = antspynet_thr
        if mask:
            mask_name = "brain_mask.nii.gz"
            if out_file:
                mask_name = fname_presuffix(out_file, suffix="_brain", use_ext=True)
            deskull_node.inputs.mask_file = mask_name
        threads, hard = get_tool_cpu_config(
            max_cpu, multicore_node_limit, limit_synth_cores
        )
        # antspynet/ITK take threads only through num_threads (a real, nipype-aware
        # reservation), like the ANTs registration node -- no soft env-var path,
        # hence the max_cpu bound (see apply_tool_num_threads).
        apply_tool_num_threads(deskull_node, threads, hard, max_cpu=max_cpu)
        if bet_surfaces:
            deskull_node.inskull_out_name = "mask_file"
    elif deskull_engine == DeskullEngine.SYNTHSTRIP:
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
    else:  # DeskullEngine.BET
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

    ``registered_node``/``registered_field`` are the backend-neutral
    ``(node, field)`` source of the moving image resampled into the reference
    space by the registration node itself (FLIRT ``out_file`` / FNIRT & ANTs
    ``warped_file`` / SynthMorph ``out_file``). It lets a caller consume the
    already-registered image without a separate apply node -- used by the CT
    workflows for the basal reference registration and the per-contrast
    ``map_moving`` MapNode.
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
        registered_node: Node = None,
        registered_field: str = None,
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
        self.registered_node = registered_node
        self.registered_field = registered_field


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
    moving_mask: str | list[Node | str] = None,
    map_moving: bool = False,
    name_prefix: str = "",
    name_suffix: str = "",
    test_run: bool = False,
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    limit_synth_cores: bool = False,
) -> RegistrationNodeWrapper:
    """
    Build a backend-neutral registration (moving -> reference) for the
    configured ``engine`` and return a :class:`RegistrationNodeWrapper`.

    ``moving_mask`` restricts the registration metric to a region of the moving
    image: on ANTs it becomes ``AntsRegistration.moving_mask``, on the FSL
    linear branch it becomes ``FLIRT.in_weight`` (the same binary map serves as
    both a metric mask and a per-voxel weight). Synth ignores it.

    ``map_moving=True`` builds the registration node as a ``MapNode`` iterating
    over the moving image, so a caller can register a *list* of moving images to
    one reference in a single node (e.g. the CT contrast series). Only the
    single-node linear/ANTs/Synth paths support it; the multi-node FSL nonlinear
    path raises.
    """

    if map_moving and engine == RegistrationEngine.FSL and non_linear:
        raise ValueError(
            "map_moving is not supported for the FSL nonlinear registration "
            "(it builds multiple chained nodes)"
        )

    def make_reg_node(interface, node_name, moving_field, **node_kwargs):
        """Node, or a MapNode iterating the moving input when map_moving."""
        if map_moving:
            return MapNode(
                interface, name=node_name, iterfield=[moving_field], **node_kwargs
            )
        return Node(interface, name=node_name, **node_kwargs)

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

        synth_morph_reg = make_reg_node(
            SynthMorphReg(), name + "_synthmorphreg", "in_file", mem_gb=mem_gb
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
            registered_node=synth_morph_reg,
            registered_field="out_file",
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

        ants_reg = make_reg_node(
            AntsRegistration(),
            name + "_antsreg",
            "moving",
            mem_gb=ResourceManager.ants_ram_requirements(),
        )
        ants_reg.long_name = name_prefix + " %s " + name_suffix
        ants_reg.inputs.transform_type = transform_type
        if test_run:
            # Same speed-for-accuracy trade the other backends make under
            # test_run (FNIRT subsampling, SynthMorph steps): the node cuts its
            # antspyx iteration schedules. Applies to both the linear (affine/
            # rigid) and the SyN stages.
            ants_reg.inputs.test_run = True
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
        apply_tool_num_threads(ants_reg, threads, hard, max_cpu=max_cpu)

        if type(moving_brain) == str:
            ants_reg.inputs.moving = moving_brain
        else:
            workflow.connect(moving_brain[0], moving_brain[1], ants_reg, "moving")
        if type(reference_brain) == str:
            ants_reg.inputs.fixed = reference_brain
        else:
            workflow.connect(reference_brain[0], reference_brain[1], ants_reg, "fixed")

        # An optional metric mask in moving space (ANTs moving_mask). Only the
        # ANTs branch honours it -- FSL's analogue is FLIRT.in_weight, wired by
        # the caller on the FSL branch; Synth has none. Used by seeg_ct's
        # electrode weighting.
        if moving_mask is not None:
            if type(moving_mask) == str:
                ants_reg.inputs.moving_mask = moving_mask
            else:
                workflow.connect(
                    moving_mask[0], moving_mask[1], ants_reg, "moving_mask"
                )

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
            registered_node=ants_reg,
            registered_field="warped_file",
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
                    inv_warp.inputs.reference = moving
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
                registered_node=fnirt,
                registered_field="warped_file",
            )
        else:
            flirt = make_reg_node(FLIRT(), name + "_flirt", "in_file")
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

            # FSL analogue of the ANTs moving_mask: a per-voxel registration
            # weight in moving space (used by seeg_ct's electrode weighting).
            if moving_mask is not None:
                if type(moving_mask) == str:
                    flirt.inputs.in_weight = moving_mask
                else:
                    workflow.connect(moving_mask[0], moving_mask[1], flirt, "in_weight")

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
                registered_node=flirt,
                registered_field="out_file",
            )


def wire_transforms(
    registration: RegistrationNodeWrapper,
    apply_node: Node,
    workflow: CustomWorkflow,
    inverse: bool = False,
) -> None:
    """
    Connect an ANTs registration wrapper's ordered transform list AND its
    paired which_to_invert flags into an ``AntsApplyTransforms`` node.

    Wiring the flags is mandatory, never optional: antspyx's ``whichtoinvert``
    default is only correct for a ``[matrix, warp]`` pair. A linear inverse (a
    lone affine ``.mat``) applied with the default would be treated as *not
    inverted* and resample silently wrong. ``AntsRegistration`` publishes the
    correct per-direction flags; this helper always forwards them.
    """
    transforms = registration.inv_transforms if inverse else registration.fwd_transforms
    which = (
        registration.inv_which_to_invert
        if inverse
        else registration.fwd_which_to_invert
    )
    if len(transforms) != 1:
        # Phase 1: a single AntsRegistration node produces the whole ordered
        # list in one output field. Stacking multiple sources (Phase 2/3) would
        # need a Merge node here.
        raise ValueError(
            "ANTs apply expects exactly one transform-list source, got %d"
            % len(transforms)
        )
    src_node, src_field = transforms[0]
    workflow.connect(src_node, src_field, apply_node, "transformlist")
    if which is not None:
        workflow.connect(which[0], which[1], apply_node, "which_to_invert")


def wire_transform_stack(
    registration_stack: list,
    apply_node: Node,
    workflow: CustomWorkflow,
    name: str,
    inverse: bool = False,
) -> None:
    """
    Connect an ordered list of ANTs registration wrappers into ONE
    ``AntsApplyTransforms`` node, as a single ``transformlist`` and a single,
    slot-for-slot matching ``which_to_invert``.

    Each wrapper contributes its own ordered transform list (one ``(node,
    field)`` source whose field is a ``List`` output) and the paired invert
    flags. The lists are concatenated by two parallel ``Merge(n,
    ravel_inputs=True)`` nodes -- ``in1`` gets the first wrapper, ``in2`` the
    second, and ``ravel_inputs`` flattens each wrapper's sub-list in place, so
    the run-time ``transformlist`` is exactly wrapper 1's transforms followed by
    wrapper 2's, and ``which_to_invert`` is flattened identically.

    **Order contract:** ``registration_stack`` IS the ``transformlist`` order,
    i.e. output space -> input space. ANTs applies a transform list
    right-to-left, so the LAST wrapper acts on the moving image first. To
    resample a func image into MNI space through func->ref and ref->mni, pass
    ``[ref_2_mni, func_2_ref]``. ``inverse=True`` swaps each wrapper's forward
    view for its inverse one but does NOT reorder the stack -- the caller still
    owns the order.

    ANTs-only: an FSL/Synth wrapper publishes no ``which_to_invert``, so mixing
    one in would leave the two merges desynchronised (fewer flags than
    transforms) and ``AntsApplyTransforms`` would reject the pair at run time.
    This raises instead, at construction time.
    """
    if len(registration_stack) < 1:
        raise ValueError("registration_stack needs at least one registration")

    transformlist_merge = Node(
        Merge(len(registration_stack), ravel_inputs=True),
        name=name + "_transformlist",
    )
    which_to_invert_merge = Node(
        Merge(len(registration_stack), ravel_inputs=True),
        name=name + "_which_to_invert",
    )

    for slot, registration in enumerate(registration_stack, start=1):
        if registration.engine != RegistrationEngine.ANTS:
            raise ValueError(
                "registration_stack accepts ANTs registration wrappers only, "
                "got %s at position %d" % (registration.engine, slot)
            )
        transforms = (
            registration.inv_transforms if inverse else registration.fwd_transforms
        )
        which = (
            registration.inv_which_to_invert
            if inverse
            else registration.fwd_which_to_invert
        )
        if len(transforms) != 1:
            raise ValueError(
                "each stacked ANTs registration must expose exactly one "
                "transform-list source, got %d at position %d" % (len(transforms), slot)
            )
        if which is None:
            raise ValueError(
                "each stacked ANTs registration must expose which_to_invert "
                "flags; position %d has none" % slot
            )
        src_node, src_field = transforms[0]
        workflow.connect(src_node, src_field, transformlist_merge, "in%d" % slot)
        workflow.connect(which[0], which[1], which_to_invert_merge, "in%d" % slot)

    workflow.connect(transformlist_merge, "out", apply_node, "transformlist")
    workflow.connect(which_to_invert_merge, "out", apply_node, "which_to_invert")


def apply_registration_node(
    name: str,
    engine: RegistrationEngine,
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
    registration: RegistrationNodeWrapper = None,
    inverse: bool = False,
    registration_stack: list[RegistrationNodeWrapper] = None,
) -> Node:
    """
    Resample ``moving`` into ``reference`` space for the given ``engine``.

    Exactly one transform source is used, and the three are mutually exclusive:

    * ``registration`` -- a single :class:`RegistrationNodeWrapper` in the same
      workflow (the ``wire_transforms`` path);
    * ``registration_stack`` -- an ordered list of ANTs wrappers concatenated
      into one ``transformlist`` + ``which_to_invert`` (the
      ``wire_transform_stack`` path, ANTS only; see its order contract);
    * ``warp`` -- a single already-composed transform field crossing a workflow
      boundary.
    """
    if registration_stack is not None:
        if registration is not None:
            raise ValueError(
                "registration and registration_stack are mutually exclusive"
            )
        if warp is not None:
            raise ValueError("warp and registration_stack are mutually exclusive")
        if engine != RegistrationEngine.ANTS:
            raise ValueError(
                "registration_stack is supported by the ANTS engine only, got %s"
                % engine
            )

    if iterfield is not None and engine == RegistrationEngine.ANTS:
        # Callers name their iterfields in the FSL/Synth vocabulary ("in_file"),
        # but AntsApplyTransforms takes the moving image as "input_image". A
        # MapNode silently ignores an iterfield its interface does not declare,
        # which would hand the whole list to a single File input at run time --
        # so the moving-image name is translated here, next to the equivalent
        # translation the connect calls below already do.
        iterfield = [
            "input_image" if field == "in_file" else field for field in iterfield
        ]

    node_class = Node if iterfield is None else MapNode
    node_kwargs = {} if iterfield is None else {"iterfield": iterfield}

    if engine == RegistrationEngine.ANTS:
        apply_node = node_class(
            AntsApplyTransforms(), name=name + "_ants_apply", **node_kwargs
        )
        apply_node.long_name = name_prefix + " %s " + name_suffix
        apply_node.inputs.interpolator = "nearestNeighbor" if labelmap else "linear"
        if type(reference) == str:
            apply_node.inputs.reference_image = reference
        else:
            workflow.connect(reference[0], reference[1], apply_node, "reference_image")

        if registration_stack is not None:
            # Several same-workflow registrations concatenated into one apply
            # (the resting-state func -> ref -> mni resample): one ordered
            # transformlist and one matching which_to_invert, both built by
            # ravel Merges (see wire_transform_stack for the order contract).
            wire_transform_stack(
                registration_stack, apply_node, workflow, name, inverse=inverse
            )
        elif registration is not None:
            # Same-workflow multi-transform apply: forward the wrapper's ordered
            # list AND its which_to_invert flags (see wire_transforms).
            wire_transforms(registration, apply_node, workflow, inverse=inverse)
        else:
            # A single composed field crossing a workflow boundary (the Phase-2
            # nonlinear-warp / CT boundary). ``transformlist`` is a List trait,
            # so the boundary's single File is lifted into a one-element list via
            # Merge(1); the field is already directional (which_to_invert was
            # baked in by AntsComposeTransform), so no which_to_invert is set.
            merge = Node(Merge(1), name=name + "_transformlist")
            workflow.connect(warp[0], warp[1], merge, "in1")
            workflow.connect(merge, "out", apply_node, "transformlist")

        if out_file:
            if type(out_file) == str:
                apply_node.inputs.out_file = out_file
            else:
                workflow.connect(out_file[0], out_file[1], apply_node, "out_file")
        if moving is None:
            pass
        elif type(moving) == str:
            apply_node.inputs.input_image = moving
        else:
            workflow.connect(moving[0], moving[1], apply_node, "input_image")

        return apply_node

    if engine == RegistrationEngine.SYNTH:
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
