import os

from configparser import SectionProxy
from nipype.pipeline.engine import Node
from nipype.interfaces.utility import IdentityInterface

from swane.config.config_enums import (
    CoreLimit,
    RegistrationEngine,
    DeskullModality,
)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.ExtractVolumes import ExtractVolumes
from swane.nipype_pipeline.nodes.AffineToRAS import AffineToRAS
from swane.nipype_pipeline.nodes.DipyDenoise import DipyDenoise
from swane.nipype_pipeline.nodes.DipyMotionCorrection import DipyMotionCorrection
from swane.nipype_pipeline.nodes.DwiBiasCorrection import DwiBiasCorrection
from swane.nipype_pipeline.nodes.DipyTensorFit import DipyTensorFit
from swane.nipype_pipeline.nodes.DipyCsdFit import DipyCsdFit
from swane.nipype_pipeline.nodes.DipyTissueClassifier import DipyTissueClassifier
from swane.nipype_pipeline.nodes.DipyTracking import DipyTracking
from swane.nipype_pipeline.nodes.DipyAtlasSLR import DipyAtlasSLR
from swane.nipype_pipeline.nodes.utils import (
    get_deskull_node,
    get_registration_node,
    apply_registration_node,
    resolve_deskull_engine,
)


# Placeholder per-node memory reservations (GB). Task 11 replaces each with an
# isolated ru_maxrss measurement on the two oracle subjects; until then these
# are conservative construction-time guesses so the plugin's prerun check has a
# figure to schedule against. They are NOT measured values.
_MEM_GB = {
    "denoise": 4,
    "motion": 4,
    "bias": 2,
    "tensorfit": 2,
    "csd": 6,
    "tissue": 4,
    "ras": 1,
    "tracking": 6,
    "slr": 8,
}


def dipy_dti_preproc_workflow(
    name: str,
    dti_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    deskull_modality: DeskullModality = DeskullModality.NODIF,
    max_cpu: int = 0,
    test_run: bool = False,
) -> CustomWorkflow:
    """
    dipy DTI preprocessing to a global tractogram (the CSD + RecoBundles engine's
    preprocessing-through-tracking half).

    The ~4-node head (dcm2niix -> ForceOrient -> b0 extract -> deskull) is
    duplicated from :func:`dti_preproc_workflow` rather than shared, so the
    validated FSL path and its golden snapshots do not churn. From the deskulled
    b0 the diffusion stream is denoised (nlmeans), motion-corrected (with
    ``reorient_bvecs``), bias-corrected (a single N4 field on the mean b0) and
    tensor-fitted; the FA map is resampled into reference space. The fODF
    (adaptive ``sh_order_max`` CSD) drives particle-filtering tractography seeded
    from the white-matter PVE mask, and a single whole-brain SLR aligns the
    resulting tractogram to the HCP842 atlas.

    Diffusion <-> reference registration and PVE resampling use **ANTs**, never
    FSL: this workflow invokes no FSL tool. The diffusion->reference affine the
    tracker needs is produced as a plain 4x4 RAS text file by :class:`AffineToRAS`
    (the ITK/LPS transform ANTs emits, inverted and expressed in RAS), not an FSL
    ``.mat`` -- that was a probtrackx requirement the dipy tracker does not share.

    New dipy nodes implement HARD_CAP only, so this factory takes no
    ``multicore_node_limit`` parameter (spec section 10).

    Parameters
    ----------
    name : str
        The workflow name.
    dti_dir : path
        The directory path of DTI dicom files.
    config : SectionProxy
        DTI workflow settings.
    synth_config : SectionProxy
        FreeSurfer Synth tools settings (deskull engine, core limiting).
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    deskull_modality : DeskullModality, optional
        antspynet brain-extraction modality for the b0 deskull node. The default
        is DeskullModality.NODIF.
    max_cpu : int, optional
        If greater than 0, the per-node core budget for the parallel dipy nodes.
        The default is 0.
    test_run : bool, optional
        If True, cut the ANTs registration iteration schedules to speed up
        prerelease test runs at the cost of accuracy. The default is False.

    Input Node Fields
    ----------
    reference : path
        T13D reference file.
    reference_brain : path
        Betted T13D reference file.

    Returns
    -------
    workflow : CustomWorkflow
        The dipy DTI preprocessing workflow.

    Output Node Fields
    ----------
    FA : path
        Fractional anisotropy map in reference space.
    tractogram : path
        Global tractogram in reference/native space (.trx). *(Phase 2 contract.)*
    tractogram_atlas : path
        The tractogram aligned to the HCP842 atlas by the single SLR (.trx).
        *(Phase 2 contract.)*
    atlas2native : path
        The atlas->native transform (text) bringing recognised bundles back.
        *(Phase 2 contract.)*

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # The registration and PVE resampling are ANTs, always: this workflow is
    # FSL-free by design (spec Goal). The SYNTH engine preference is not consulted
    # for the diffusion registration here.
    engine = RegistrationEngine.ANTS

    # A per-node core budget for the parallel dipy nodes; every node still
    # declares a real n_procs (HARD_CAP).
    parallel_cpu = max_cpu if max_cpu and max_cpu > 0 else 1

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference_brain", "reference"]), name="inputnode"
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=["FA", "tractogram", "tractogram_atlas", "atlas2native"]
        ),
        name="outputnode",
    )

    # -- Shared head (duplicated from dti_preproc_workflow:137-173) ----------- #

    # NODE 1: Conversion dicom -> nifti
    conversion = Node(CustomDcm2niix(), name="dipy_conv")
    conversion.inputs.source_dir = dti_dir
    conversion.inputs.out_filename = "dti"
    conversion.inputs.bids_format = False
    conversion.inputs.request_dti = True
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 1b: Orienting in radiological convention
    reorient = Node(ForceOrient(), name="dipy_reOrient")
    workflow.connect(conversion, "converted_files", reorient, "in_file")

    # NODE 2: b0 image extraction
    nodif = Node(ExtractVolumes(), name="dipy_nodif")
    nodif.long_name = "b0 extraction"
    nodif.inputs.start_volume = 0
    nodif.inputs.num_volumes = 1
    nodif.inputs.out_file = "nodif.nii.gz"
    workflow.connect(reorient, "out_file", nodif, "in_file")

    # NODE 3: Scalp removal from b0 image
    b0_deskull = get_deskull_node(
        name="dipy_deskull",
        name_prefix="DTI",
        deskull_engine=resolve_deskull_engine(synth_config),
        deskull_modality=deskull_modality,
        mask=True,
        bet_thr=0.3,
        bet_robust=True,
        bet_threshold=True,
        out_file="nodif_brain.nii.gz",
        max_cpu=max_cpu,
        multicore_node_limit=CoreLimit.HARD_CAP,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    workflow.connect(nodif, "out_file", b0_deskull, "in_file")

    # -- Diffusion stream: denoise -> motion -> bias -> tensor (spec section 5) #

    # NODE 4: nlmeans denoising
    denoise = Node(DipyDenoise(), name="dipy_denoise")
    denoise._mem_gb = _MEM_GB["denoise"]
    denoise.inputs.num_threads = parallel_cpu
    denoise.n_procs = parallel_cpu
    workflow.connect(reorient, "out_file", denoise, "in_file")
    workflow.connect(conversion, "bvals", denoise, "bval")
    workflow.connect(conversion, "bvecs", denoise, "bvec")

    # NODE 5: motion correction + reorient_bvecs (parallel over volumes)
    motion = Node(DipyMotionCorrection(), name="dipy_motion")
    motion._mem_gb = _MEM_GB["motion"]
    motion.inputs.parallel = True
    motion.inputs.num_threads = parallel_cpu
    motion.n_procs = parallel_cpu
    workflow.connect(denoise, "out_file", motion, "in_file")
    workflow.connect(conversion, "bvals", motion, "bval")
    workflow.connect(conversion, "bvecs", motion, "bvec")

    # NODE 6: single N4 field on the mean b0, applied to all volumes
    bias = Node(DwiBiasCorrection(), name="dipy_bias")
    bias._mem_gb = _MEM_GB["bias"]
    bias.inputs.num_threads = parallel_cpu
    bias.n_procs = parallel_cpu
    workflow.connect(motion, "out_file", bias, "in_file")
    workflow.connect(motion, "out_bval", bias, "bval")

    # NODE 7: tensor fit -> FA
    tensorfit = Node(DipyTensorFit(), name="dipy_tensorfit")
    tensorfit._mem_gb = _MEM_GB["tensorfit"]
    tensorfit.n_procs = 1
    workflow.connect(bias, "out_file", tensorfit, "in_file")
    workflow.connect(motion, "out_bval", tensorfit, "bval")
    workflow.connect(motion, "out_bvec", tensorfit, "bvec")
    workflow.connect(b0_deskull, "mask_file", tensorfit, "mask")

    # NODE 8: b0 linear registration in reference space (ANTs, affine only)
    dif2ref = get_registration_node(
        name="dif2ref",
        name_prefix="DTI",
        name_suffix="to reference",
        engine=engine,
        workflow=workflow,
        moving=[nodif, "out_file"],
        moving_brain=[b0_deskull, "out_file"],
        reference=[inputnode, "reference"],
        reference_brain=[inputnode, "reference_brain"],
        flirt_cost="corratio",
        non_linear=False,
        inverse=True,
        test_run=test_run,
        max_cpu=max_cpu,
        multicore_node_limit=CoreLimit.HARD_CAP,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )

    # FA -> reference space (forward, diff->ref)
    fa_2_ref = apply_registration_node(
        name="fa_2_ref",
        name_prefix="FA",
        name_suffix="to reference",
        engine=engine,
        workflow=workflow,
        warp=None,
        registration=dif2ref,
        moving=[tensorfit, "fa"],
        reference=[inputnode, "reference"],
        out_file="r-FA.nii.gz",
        non_linear=False,
    )
    workflow.connect(fa_2_ref, "out_file", outputnode, "FA")

    is_tractography = config.getboolean_safe("tractography")
    if is_tractography:
        # -- Tissue side branch: HMRF on the T1 reference_brain -> 3 PVE maps -- #
        tissue = Node(DipyTissueClassifier(), name="dipy_tissue")
        tissue._mem_gb = _MEM_GB["tissue"]
        tissue.n_procs = 1
        workflow.connect(inputnode, "reference_brain", tissue, "in_file")

        # Each PVE map is resampled ref->diff into the diffusion grid (the b0),
        # so the CMC criterion and the seed mask live in tracking space. The
        # inverse apply forwards which_to_invert (mandatory for a linear
        # inverse, see wire_transforms).
        pve_applies = {}
        for tissue_field in ("pve_wm", "pve_gm", "pve_csf"):
            pve_applies[tissue_field] = apply_registration_node(
                name="%s_2_diff" % tissue_field,
                name_prefix="PVE",
                name_suffix="to diffusion",
                engine=engine,
                workflow=workflow,
                warp=None,
                registration=dif2ref,
                inverse=True,
                moving=[tissue, tissue_field],
                reference=[nodif, "out_file"],
                out_file="r-%s.nii.gz" % tissue_field,
                non_linear=False,
            )

        # -- CSD fODF -------------------------------------------------------- #
        csd = Node(DipyCsdFit(), name="dipy_csd")
        csd._mem_gb = _MEM_GB["csd"]
        csd.inputs.num_threads = parallel_cpu
        csd.n_procs = parallel_cpu
        workflow.connect(bias, "out_file", csd, "in_file")
        workflow.connect(motion, "out_bval", csd, "bval")
        workflow.connect(motion, "out_bvec", csd, "bvec")
        workflow.connect(b0_deskull, "mask_file", csd, "mask")

        # -- diff->ref affine as a 4x4 RAS text file (ANTs ITK -> RAS) ------- #
        dif2ref_to_ras = Node(AffineToRAS(), name="dif2ref_to_ras")
        dif2ref_to_ras.long_name = "DTI-to-reference affine RAS conversion"
        dif2ref_to_ras._mem_gb = _MEM_GB["ras"]
        dif2ref_to_ras.n_procs = 1
        dif2ref_to_ras.inputs.in_fmt = "itk"
        fwd_node, fwd_field = dif2ref.fwd_transforms[0]
        workflow.connect(fwd_node, fwd_field, dif2ref_to_ras, "in_transform")
        workflow.connect(b0_deskull, "out_file", dif2ref_to_ras, "source_file")
        workflow.connect(inputnode, "reference_brain", dif2ref_to_ras, "reference_file")

        # -- Particle-filtering tractography (WM seeds, CMC) ----------------- #
        tracking = Node(DipyTracking(), name="dipy_tracking")
        tracking._mem_gb = _MEM_GB["tracking"]
        tracking.inputs.num_threads = parallel_cpu
        tracking.n_procs = parallel_cpu
        tracking.inputs.seed_density = config.getint_safe("seed_density")
        tracking.inputs.max_angle = config.getfloat_safe("max_angle")
        tracking.inputs.step_size = config.getfloat_safe("step_size")
        workflow.connect(csd, "shm_coeff", tracking, "shm_coeff")
        workflow.connect(pve_applies["pve_wm"], "out_file", tracking, "pve_wm")
        workflow.connect(pve_applies["pve_gm"], "out_file", tracking, "pve_gm")
        workflow.connect(pve_applies["pve_csf"], "out_file", tracking, "pve_csf")
        # A StatefulTractogram needs the reference image (affine + dimensions),
        # not just the diff->ref affine.
        workflow.connect(inputnode, "reference", tracking, "reference")
        workflow.connect(dif2ref_to_ras, "out_ras", tracking, "affine_diff2ref")
        workflow.connect(tracking, "tractogram", outputnode, "tractogram")

        # -- Whole-brain SLR against the HCP842 atlas (once) ----------------- #
        atlas_slr = Node(DipyAtlasSLR(), name="dipy_slr")
        atlas_slr._mem_gb = _MEM_GB["slr"]
        atlas_slr.n_procs = 1
        atlas_slr.inputs.num_threads = 1
        atlas_slr.inputs.atlas_dir = os.path.join(os.path.expanduser("~"), ".dipy")
        workflow.connect(tracking, "tractogram", atlas_slr, "tractogram")
        workflow.connect(atlas_slr, "tractogram_atlas", outputnode, "tractogram_atlas")
        workflow.connect(atlas_slr, "atlas2native", outputnode, "atlas2native")

    return workflow
