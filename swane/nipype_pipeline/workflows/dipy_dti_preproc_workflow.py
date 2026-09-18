import os

from configparser import SectionProxy
from nipype.pipeline.engine import Node, MapNode
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
from swane.nipype_pipeline.nodes.DwiCrop import DwiCrop
from swane.nipype_pipeline.nodes.DipyDenoise import DipyDenoise
from swane.nipype_pipeline.nodes.DipyMotionCorrection import DipyMotionCorrection
from swane.nipype_pipeline.nodes.DwiBiasCorrection import DwiBiasCorrection
from swane.nipype_pipeline.nodes.DipyTensorFit import DipyTensorFit
from swane.nipype_pipeline.nodes.DipyCsdFit import DipyCsdFit
from swane.nipype_pipeline.nodes.DipyTissueClassifier import DipyTissueClassifier
from swane.nipype_pipeline.nodes.DipyTracking import DipyTracking
from swane.nipype_pipeline.nodes.DipyAtlasSLR import DipyAtlasSLR
from swane.nipype_pipeline.nodes.DipyTractogramChunker import DipyTractogramChunker
from swane.nipype_pipeline.nodes.DipyRecoBundles import DipyRecoBundlesBuild
from swane.nipype_pipeline.nodes.ram_estimators import (
    DipyCropRamEstimator,
    DipyCsdRamEstimator,
    DipyMotionRamEstimator,
    DipySlrRamEstimator,
    DipyTissueRamEstimator,
    DipyTrackingRamEstimator,
    RecoBundlesRamEstimator,
    DipyRecoBundlesChunkerRamEstimator,
)
from swane.nipype_pipeline.nodes.utils import (
    get_deskull_node,
    get_registration_node,
    apply_registration_node,
    resolve_deskull_engine,
    resolve_registration_engine,
)

# Per-node memory reservations (GB) for static nodes.
#
# motion, tracking, tissue and csd are sized at scheduling time by their
# respective estimators: DipyMotionRamEstimator, DipyTrackingRamEstimator,
# DipyTissueRamEstimator, and DipyCsdRamEstimator.
# crop and slr are sized by DipyCropRamEstimator and DipySlrRamEstimator.
_MEM_GB = {
    "denoise": 2,
    "bias": 1,
    "tensorfit": 2,
    "ras": 1,
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
    tensor-fitted; the FA map is resampled into reference space (and, in
    diffusion space, drives tracking's own stopping criterion). The fODF
    (adaptive ``sh_order_max`` CSD) drives probabilistic tractography
    (FA-threshold stopping) seeded from the white-matter PVE mask, and a
    single whole-brain SLR aligns the resulting tractogram to the HCP842
    atlas.

    The dipy engine's own steps (denoise, motion, bias, CSD, tracking, SLR) are
    FSL-free by design (spec Goal). The two *abstracted* steps -- brain
    extraction and diffusion<->reference registration -- keep honouring the
    user's global engine choice, FSL included (spec section 1). The
    diffusion->reference affine the tracker needs is produced as a plain 4x4 RAS
    text file by :class:`AffineToRAS`, which handles both the ITK/LPS transform
    ANTs emits and the FLIRT ``.mat`` FSL emits (either inverted and expressed in
    RAS); it is never an FSL ``.mat`` on output -- that was a probtrackx
    requirement the dipy tracker does not share.

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
        If True, cut the registration iteration schedules of the configured
        engine to speed up prerelease test runs at the cost of accuracy. The
        default is False.

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

    # Registration is an abstracted step: it follows the user's global engine
    # choice, FSL included (spec section 1). SynthMorph is avoided for the
    # diffusion registration (non-deterministic, and its diff<->ref outputs are
    # emitted as the ANTs transform-list view, not an FSL .mat), so SYNTH falls
    # back to FSL exactly as dti_preproc_workflow does.
    engine = resolve_registration_engine(synth_config, allow_ants=True)
    if engine == RegistrationEngine.SYNTH:
        engine = RegistrationEngine.FSL

    # A per-node core budget for the parallel dipy nodes; each sets num_threads,
    # from which nipype derives a real n_procs reservation (HARD_CAP). max_cpu==0
    # means "auto/all cores" upstream, so it must clamp to 1 here, never 0.
    parallel_cpu = max_cpu if max_cpu and max_cpu > 0 else 1

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference_brain", "reference"]), name="inputnode"
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "FA",
                "tractogram",
                "tractogram_atlas",
                "atlas2native",
                # Phase-2 additive outputs (Phase-1's four above are unchanged):
                # the shared per-chunk RecoBundles build pickles and the chunk
                # .trx they were built on. The recognise nodes reload the chunk
                # streamlines (the pickle deliberately omits them), so both must
                # be published for the per-tract bundle workflow to consume.
                "recobundles_builds",
                "recobundles_chunks",
            ]
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

    # NODE 1c: Upfront brain bounding-box crop of the 4D series (median_otsu mask
    # on the mean of all volumes -- the motion envelope, since this runs before
    # motion correction), so every downstream node works on the brain sub-box
    # instead of the empty FOV margin (spec section "C1"). bvals/bvecs are
    # crop-invariant and are not needed here; they keep flowing from conversion to
    # the consumers. The affine is shifted (shift_affine_for_crop) so world
    # coordinates survive the crop. median_otsu is single-threaded scipy work, so
    # num_threads (and the derived n_procs) is 1 -- honest HARD_CAP accounting,
    # not a parallel reservation.
    crop = Node(DwiCrop(), name="dipy_crop")
    # RAM is reserved at scheduling time from the 4D series' voxel x volume
    # count (one-way: median_otsu/numpy here are single-threaded, no lever).
    # The static value is only the negotiation-failed fail-safe.
    crop._mem_gb = DipyCropRamEstimator.STATIC_FALLBACK_GB
    crop.ram_estimator = DipyCropRamEstimator()
    crop.inputs.num_threads = 1
    crop.inputs.out_file = "crop_dti.nii.gz"
    workflow.connect(reorient, "out_file", crop, "in_file")

    # NODE 2: b0 image extraction
    nodif = Node(ExtractVolumes(), name="dipy_nodif")
    nodif.long_name = "b0 extraction"
    nodif.inputs.start_volume = 0
    nodif.inputs.num_volumes = 1
    nodif.inputs.out_file = "nodif.nii.gz"
    workflow.connect(crop, "out_file", nodif, "in_file")

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
        # parallel_cpu, not raw max_cpu: under HARD_CAP the helper reserves
        # exactly max_cpu cores, and max_cpu==0 ("auto") must land as 1, not 0.
        max_cpu=parallel_cpu,
        multicore_node_limit=CoreLimit.HARD_CAP,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    workflow.connect(nodif, "out_file", b0_deskull, "in_file")

    # -- Diffusion stream: denoise -> motion -> bias -> tensor (spec section 5) #

    # NODE 4: nlmeans denoising
    denoise = Node(DipyDenoise(), name="dipy_denoise")
    denoise._mem_gb = _MEM_GB["denoise"]
    # n_procs is left to nipype's default, which returns interface.num_threads
    # when set (as it is here) -- an explicit n_procs would duplicate that.
    denoise.inputs.num_threads = parallel_cpu
    workflow.connect(crop, "out_file", denoise, "in_file")
    workflow.connect(conversion, "bvals", denoise, "bval")
    workflow.connect(conversion, "bvecs", denoise, "bvec")

    # NODE 5: motion correction + reorient_bvecs (parallel over volumes)
    motion = Node(DipyMotionCorrection(), name="dipy_motion")
    # RAM is negotiated at scheduling time, when the real input is on disk: the
    # driver holds the whole 4D series (voxels x volumes) while each pool worker
    # adds its own 3D share, so the estimator prices both terms and walks the
    # worker count down until the estimate fits the workflow RAM budget. The
    # static value below is only the fail-safe used when the negotiation cannot
    # run (see MonitoredMultiProcPlugin._negotiate_ram).
    motion._mem_gb = DipyMotionRamEstimator.STATIC_FALLBACK_GB
    motion.ram_estimator = DipyMotionRamEstimator()
    motion.inputs.parallel = True
    motion.inputs.num_threads = parallel_cpu
    workflow.connect(denoise, "out_file", motion, "in_file")
    workflow.connect(conversion, "bvals", motion, "bval")
    workflow.connect(conversion, "bvecs", motion, "bvec")

    # NODE 6: single N4 field on the mean b0, applied to all volumes
    bias = Node(DwiBiasCorrection(), name="dipy_bias")
    bias._mem_gb = _MEM_GB["bias"]
    bias.inputs.num_threads = parallel_cpu
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

    # NODE 8: b0 linear registration in reference space (engine-neutral, affine
    # only). ANTs: Rigid AntsRegistration; FSL: FLIRT (+ ConvertXFM inverse).
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
        # parallel_cpu, not raw max_cpu: HARD_CAP reserves exactly this many
        # cores and max_cpu==0 ("auto") must land as 1 (FSL FLIRT ignores it).
        max_cpu=parallel_cpu,
        multicore_node_limit=CoreLimit.HARD_CAP,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )

    # FA -> reference space (forward, diff->ref). Both transform views are
    # passed: the ANTs apply consumes ``registration`` (its ordered list +
    # which_to_invert), the FSL apply consumes ``warp`` (the FLIRT .mat); each
    # engine ignores the other's (see apply_registration_node).
    fa_2_ref = apply_registration_node(
        name="fa_2_ref",
        name_prefix="FA",
        name_suffix="to reference",
        engine=engine,
        workflow=workflow,
        warp=[dif2ref.out_registered_node, dif2ref.warp],
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
        # RAM is reserved at scheduling time from the T1 voxel count: HMRF peak
        # is linear in voxels. The estimator is classic (one-way) -- the node
        # pins OMP=1 internally and has no thread lever, so there is nothing to
        # tune.
        # The static value below is only the fail-safe used when the negotiation
        # cannot run (see MonitoredMultiProcPlugin._negotiate_ram).
        tissue._mem_gb = DipyTissueRamEstimator.STATIC_FALLBACK_GB
        tissue.ram_estimator = DipyTissueRamEstimator()
        tissue.n_procs = 1
        workflow.connect(inputnode, "reference_brain", tissue, "in_file")

        # The WM PVE map is resampled ref->diff into the diffusion grid (the
        # b0), so the seed mask lives in tracking space. Both inverse
        # transform views are passed: the ANTs apply consumes ``registration``
        # with ``inverse=True`` (forwarding which_to_invert, mandatory for a
        # linear inverse -- see wire_transforms); the FSL apply consumes
        # ``warp``, the pre-inverted ref->diff ConvertXFM .mat.
        pve_wm_2_diff = apply_registration_node(
            name="pve_wm_2_diff",
            name_prefix="PVE",
            name_suffix="to diffusion",
            engine=engine,
            workflow=workflow,
            warp=[dif2ref.inv_warp_node, dif2ref.inv_warp],
            registration=dif2ref,
            inverse=True,
            moving=[tissue, "pve_wm"],
            reference=[nodif, "out_file"],
            out_file="r-pve_wm.nii.gz",
            non_linear=False,
        )

        # -- CSD fODF -------------------------------------------------------- #
        csd = Node(DipyCsdFit(), name="dipy_csd")
        # RAM is negotiated at scheduling time from the real input: the estimate
        # is driven by the input sequence's voxel count (which sizes both the 4D
        # buffer and every per-voxel output array) and the adaptive SH order, and
        # dipy's peaks_from_model has two structurally different branches --
        # parallel holds three full-volume copies of those arrays, serial holds
        # one -- so the estimator scans the worker count down to the serial rung
        # rather than halving. The static value below is only the fail-safe used
        # when the negotiation cannot run (see
        # MonitoredMultiProcPlugin._negotiate_ram).
        csd._mem_gb = DipyCsdRamEstimator.STATIC_FALLBACK_GB
        csd.ram_estimator = DipyCsdRamEstimator()
        csd.inputs.num_threads = parallel_cpu
        workflow.connect(bias, "out_file", csd, "in_file")
        workflow.connect(motion, "out_bval", csd, "bval")
        workflow.connect(motion, "out_bvec", csd, "bvec")
        workflow.connect(b0_deskull, "mask_file", csd, "mask")

        # -- diff->ref affine as a 4x4 RAS text file --------------------------- #
        # The forward transform is the ANTs ITK affine or the FLIRT .mat,
        # depending on the engine; AffineToRAS reads whichever via nitransforms.
        dif2ref_to_ras = Node(AffineToRAS(), name="dif2ref_to_ras")
        dif2ref_to_ras.long_name = "DTI-to-reference affine RAS conversion"
        dif2ref_to_ras._mem_gb = _MEM_GB["ras"]
        dif2ref_to_ras.n_procs = 1
        dif2ref_to_ras.inputs.in_fmt = (
            "fsl" if engine == RegistrationEngine.FSL else "itk"
        )
        fwd_node, fwd_field = dif2ref.fwd_transforms[0]
        workflow.connect(fwd_node, fwd_field, dif2ref_to_ras, "in_transform")
        workflow.connect(b0_deskull, "out_file", dif2ref_to_ras, "source_file")
        workflow.connect(inputnode, "reference_brain", dif2ref_to_ras, "reference_file")

        # -- Probabilistic tractography (WM seeds, FA stop) ------------------ #
        tracking = Node(DipyTracking(), name="dipy_tracking")
        # RAM is negotiated at scheduling time, when the real inputs are on disk:
        # the peak is dominated by the incompressible full-FOV working set, while
        # seed_buffer_fraction and trx_chunk_size are quality-neutral levers the
        # estimator walks down until the estimate fits the workflow RAM budget.
        # The static value below is only the fail-safe used when the negotiation
        # cannot run (see MonitoredMultiProcPlugin._negotiate_ram).
        tracking._mem_gb = DipyTrackingRamEstimator.STATIC_FALLBACK_GB
        tracking.ram_estimator = DipyTrackingRamEstimator()
        tracking.inputs.num_threads = parallel_cpu
        tracking.inputs.seed_density = config.getint_safe("seed_density")
        tracking.inputs.max_angle = config.getfloat_safe("max_angle")
        tracking.inputs.step_size = config.getfloat_safe("step_size")
        workflow.connect(csd, "shm_coeff", tracking, "shm_coeff")
        workflow.connect(pve_wm_2_diff, "out_file", tracking, "pve_wm")
        # tensorfit's FA is already in diffusion space (the same grid as
        # shm_coeff/nodif_brain) -- not fa_2_ref's reference-space copy -- so
        # the stopping criterion needs no further resampling.
        workflow.connect(tensorfit, "fa", tracking, "fa")
        # nodif_brain is on the exact nodif grid: reorient -> denoise -> motion
        # -> bias -> csd each re-stamp the original affine/header unchanged
        # (voxelwise ops / resample-back-onto-input-grid), so the crop bbox it
        # drives lines up with shm_coeff without any further resampling.
        workflow.connect(b0_deskull, "out_file", tracking, "nodif_brain")
        # A StatefulTractogram needs the reference image (affine + dimensions),
        # not just the diff->ref affine.
        workflow.connect(inputnode, "reference", tracking, "reference")
        workflow.connect(dif2ref_to_ras, "out_ras", tracking, "affine_diff2ref")
        workflow.connect(tracking, "tractogram", outputnode, "tractogram")

        # -- Whole-brain SLR against the HCP842 atlas (once) ----------------- #
        atlas_slr = Node(DipyAtlasSLR(), name="dipy_slr")
        # RAM is reserved at scheduling time from the subject tractogram's
        # point count (one-way: no quality-neutral lever, see
        # DipySlrRamEstimator). The static value is only the
        # negotiation-failed fail-safe.
        atlas_slr._mem_gb = DipySlrRamEstimator.STATIC_FALLBACK_GB
        atlas_slr.ram_estimator = DipySlrRamEstimator()
        # num_threads=1 already makes nipype's derived n_procs == 1.
        atlas_slr.inputs.num_threads = 1
        atlas_slr.inputs.atlas_dir = os.path.join(os.path.expanduser("~"), ".dipy")
        workflow.connect(tracking, "tractogram", atlas_slr, "tractogram")
        workflow.connect(atlas_slr, "tractogram_atlas", outputnode, "tractogram_atlas")
        workflow.connect(atlas_slr, "atlas2native", outputnode, "atlas2native")

        # -- Shared RecoBundles build (clustering), once per subject --------- #
        # The RecoBundles cost is the whole-tractogram QuickBundlesX clustering
        # (RecoBundles.__init__); recognise is cheap. So the build runs here,
        # once, shared across every tract, and each per-tract bundle workflow
        # only recognises (spec section 6 / user design 2026-09-07). The
        # atlas-space tractogram is first split into 1..N representative
        # sub-tractograms (strided, not contiguous) so a chunked build's peak
        # RAM is bounded; the build is a MapNode over those chunks. Both the
        # pickled builds and the chunk .trx are published: the recognise node
        # reloads the chunk streamlines (they are not stored in the pickle).
        # n_chunks is chosen at scheduling time by the chunker's estimator from
        # the real tractogram's point count and the RAM budget, so each
        # downstream RecoBundles chunk fits; the static value is only the
        # negotiation-failed fail-safe.
        chunker = Node(DipyTractogramChunker(), name="dipy_chunker")
        chunker._mem_gb = RecoBundlesRamEstimator.STATIC_FALLBACK_GB
        chunker.ram_estimator = DipyRecoBundlesChunkerRamEstimator()
        chunker.n_procs = 1
        workflow.connect(atlas_slr, "tractogram_atlas", chunker, "tractogram_atlas")

        recobundles_build = MapNode(
            DipyRecoBundlesBuild(),
            name="dipy_recobundles_build",
            iterfield=["tractogram_chunk"],
        )
        # The build is a whole-(sub-)tractogram clustering: RAM is reserved at
        # scheduling time from each chunk's point count (linear in points). A
        # MapNode propagates the estimator to each per-chunk mapped node, so each
        # is priced from its own chunk. The static value is only the
        # negotiation-failed fail-safe. num_threads pins the clustering's
        # OMP/BLAS; nipype derives n_procs from it (HARD_CAP).
        recobundles_build._mem_gb = RecoBundlesRamEstimator.STATIC_FALLBACK_GB
        recobundles_build.ram_estimator = RecoBundlesRamEstimator()
        recobundles_build.inputs.num_threads = parallel_cpu
        workflow.connect(chunker, "chunks", recobundles_build, "tractogram_chunk")
        workflow.connect(
            recobundles_build, "recobundles_pickle", outputnode, "recobundles_builds"
        )
        workflow.connect(chunker, "chunks", outputnode, "recobundles_chunks")

    return workflow
