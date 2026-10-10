from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.interfaces.geometry.ForceOrient import ForceOrient
from swane.nipype_pipeline.interfaces.geometry.CropFov import CropFov
from swane.nipype_pipeline.interfaces.ants.AntsN4BiasFieldCorrection import (
    AntsN4BiasFieldCorrection,
)
from swane.nipype_pipeline.interfaces.ants.AntsAtropos import AntsAtropos
from swane.nipype_pipeline.interfaces.stats.ZIntNorm import ZIntNorm
from swane.nipype_pipeline.interfaces.ram_estimators import FastRamEstimator
from swane.nipype_pipeline.interfaces.utils import (
    apply_tool_num_threads,
    get_deskull_node,
    get_tool_cpu_config,
    resolve_deskull_engine,
    resolve_segmentation_engine,
)
from configparser import SectionProxy
from swane.nipype_pipeline.interfaces.niimath import NiiMathRobustFov
from swane.nipype_pipeline.interfaces.niimath import ApplyMask
from nipype.interfaces.fsl import FAST
from nipype.interfaces.utility import IdentityInterface
from nipype import Node
from swane.config.config_enums import DeskullModality, SegmentationEngine
from swane.utils.ResourceManager import ResourceManager


def ref_workflow(
    name: str,
    dicom_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    deskull_modality: DeskullModality = DeskullModality.T1,
    max_cpu: int = 0,
    test_run: bool = False,
    tissue_segmentation: bool = False,
) -> CustomWorkflow:
    """
    T13D workflow to use as reference.

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The file path of the DICOM files.
    config: SectionProxy
        workflow settings.
    synth_config: SectionProxy
        Synth tools settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    deskull_modality : DeskullModality, optional
        antspynet brain-extraction modality for the deskull node. The default
        is DeskullModality.T1.
    max_cpu : int, optional
        If greater than 0, limit the core usage of Synth tools and of the
        ITK-based Atropos segmentation node. The default is 0.
    test_run : bool, optional
        If True, cap the N4 bias field correction iterations (and, when
        tissue_segmentation is True, the segmentation iterations) to speed up
        prerelease test runs at the cost of accuracy. The default is False.
    tissue_segmentation : bool, optional
        If True, add a single three-class tissue segmentation of the reference
        brain (engine from the ``segmentation_engine`` Synth preference),
        shared by every workflow that needs tissue maps. The default is False.

    Input Node Fields
    ----------
    -

    Returns
    -------
    workflow : CustomWorkflow
        The T13D reference workflow.

    Output Node Fields
    ----------
    reference : path
        T13D.
    reference_brain : path
        Betted T13D.
    reference_mask : path
        Brain mask from T13D bet command.
    uncorrected_reference : path
        Uncorrected T13D.
    uncorrected_reference_brain : path
        Uncorrected betted T13D.
    tissue_pve : list of path
        Tissue partial volume / posterior maps ordered [CSF, GM, WM]
        (tissue_segmentation only).
    tissue_restored : path
        Bias-corrected betted T13D matching tissue_pve: the FAST restored
        image (FSL engine) or reference_brain (ANTS engine)
        (tissue_segmentation only).

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "reference",
                "reference_brain",
                "ref_mask",
                "uncorrected_reference",
                "uncorrected_reference_brain",
                "tissue_pve",
                "tissue_restored",
            ]
        ),
        name="outputnode",
    )

    # NODE 1: Conversion dicom -> nifti
    conversion = Node(CustomDcm2niix(), name="%s_conv" % name)
    conversion.inputs.source_dir = dicom_dir
    conversion.inputs.bids_format = False
    conversion.inputs.out_filename = "converted"
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    ref_reOrient = Node(ForceOrient(), name="%s_reOrient" % name)
    workflow.connect(conversion, "converted_files", ref_reOrient, "in_file")

    # NODE 3: Crop neck
    ref_robustfov = Node(NiiMathRobustFov(), name="%s_robustfov" % name)
    ref_robustfov.inputs.out_roi = "ref_robustfov.nii.gz"
    workflow.connect(ref_reOrient, "out_file", ref_robustfov, "in_file")

    # NODE 4: Crop FOV larger than 256mm for subsequent freesurfer
    ref_reScale = Node(CropFov(), name="%s_reScale" % name)
    ref_reScale.long_name = "Crop large FOV"
    ref_reScale.inputs.max_dim = 256
    ref_reScale.inputs.out_file = "ref_uncorrected.nii.gz"
    workflow.connect(ref_robustfov, "out_roi", ref_reScale, "in_file")

    # NODE 5: Scalp removal
    ref_deskull = get_deskull_node(
        name="ref_deskull_biased",
        deskull_engine=resolve_deskull_engine(synth_config),
        deskull_modality=deskull_modality,
        mask=True,
        bet_thr=config.getfloat_safe("bet_thr"),
        antspynet_thr=config.getfloat_safe("antspynet_thr"),
        bet_robust=True,
        bet_bias_correction=config.getboolean_safe("bet_bias_correction"),
        synth_exclude_csf=True,
        max_cpu=max_cpu,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    workflow.connect(ref_reScale, "out_file", ref_deskull, "in_file")

    ref_bias_correction = Node(
        AntsN4BiasFieldCorrection(), name="ref_bias_correction", mem_gb=2
    )
    ref_bias_correction.inputs.out_file = "ref.nii.gz"
    # The reference N4 is tuned towards FSL FAST, the engine the FLAT1 atlas
    # was built with, rather than towards a full correction: an N4-corrected
    # brain brings the Atropos segmentation and the FLAIR/T1 ratio closer to
    # FAST, but FAST removes the bias field only partially and a full-strength
    # N4 inflates the FLAT1 junction/extension maps. Among the N4/Atropos
    # settings evaluated (B-spline distance, resolution levels, iterations,
    # convergence tolerance, alternating N4/Atropos rounds), a coarse 150 mm
    # B-spline mesh with two short levels ([20, 10]) came closest to FAST. It
    # is an approximation, not an equivalent: FAST corrects proportionally
    # less when the bias is mild, which no N4 setting reproduces, so a
    # residual offset remains, and strongly biased acquisitions (e.g.
    # multichannel head coils without vendor intensity normalization) still
    # diverge from the atlas engine. This same N4 output is the reference
    # used by the registrations.
    ref_bias_correction.inputs.spline_distance = 150
    ref_bias_correction.inputs.max_iterations = [20, 10]
    if max_cpu != 0:
        ref_bias_correction.inputs.num_threads = max_cpu
    if test_run:
        # halve the per-level iterations to speed prerelease runs
        ref_bias_correction.inputs.max_iterations = [10, 5]
    workflow.connect(ref_reScale, "out_file", ref_bias_correction, "in_file")
    workflow.connect(ref_deskull, "mask_file", ref_bias_correction, "mask_file")

    ref_corrected_deskull = Node(ApplyMask(), name="ref_corrected_deskull")
    ref_corrected_deskull.inputs.out_file = "ref_brain.nii.gz"
    workflow.connect(ref_bias_correction, "out_file", ref_corrected_deskull, "in_file")
    workflow.connect(ref_deskull, "mask_file", ref_corrected_deskull, "mask_file")

    workflow.connect(ref_bias_correction, "out_file", outputnode, "reference")
    workflow.connect(ref_corrected_deskull, "out_file", outputnode, "reference_brain")
    workflow.connect(ref_deskull, "mask_file", outputnode, "ref_mask")
    workflow.connect(ref_reScale, "out_file", outputnode, "uncorrected_reference")
    workflow.connect(ref_deskull, "out_file", outputnode, "uncorrected_reference_brain")

    if tissue_segmentation:
        # NODE 6: three-class tissue segmentation shared by every consumer
        # (FLAT1, dipy tractography seeding, NILEARN resting-state nuisance
        # ROIs), engine-selectable.
        segmentation_engine = resolve_segmentation_engine(synth_config)
        if segmentation_engine == SegmentationEngine.ANTS:
            # Atropos segments the N4-corrected brain (see ref_bias_correction),
            # which is also the matching restored image.
            segmentation = Node(
                AntsAtropos(),
                name="ref_segmentation",
                mem_gb=ResourceManager.atropos_ram_requirements(),
            )
            if test_run:
                # cut EM iterations to speed prerelease runs at the cost of accuracy
                segmentation.inputs.iterations = 3
            if max_cpu != 0:
                # Atropos runs on ITK: its thread count flows only through
                # num_threads (a nipype-aware reservation the node exports as
                # ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS at run time), exactly
                # like the antspynet deskull node. Left unbudgeted when max_cpu
                # is 0.
                threads = get_tool_cpu_config(
                    max_cpu, synth_config.getboolean_safe("limit_cores")
                )
                apply_tool_num_threads(segmentation, threads, max_cpu=max_cpu)
            workflow.connect(ref_corrected_deskull, "out_file", segmentation, "in_file")
            workflow.connect(
                ref_corrected_deskull, "out_file", outputnode, "tissue_restored"
            )
        else:  # SegmentationEngine.FSL
            # FAST runs its own bias correction: feed it the uncorrected brain
            # and expose its restored image.
            segmentation = Node(FAST(), name="ref_segmentation", mem_gb=4)
            segmentation.ram_estimator = FastRamEstimator()
            segmentation.inputs.img_type = 1  # param -t
            segmentation.inputs.number_classes = 3  # param n
            segmentation.inputs.hyper = 0.1  # param -H
            segmentation.inputs.bias_lowpass = 40  # param -l
            segmentation.inputs.output_biascorrected = True  # param -B
            if test_run:
                # FSL defaults: -I 4, -W 15, -O 4. Aggressively cut all three.
                segmentation.inputs.bias_iters = 1  # param -I
                segmentation.inputs.segment_iters = 5  # param -W
                segmentation.inputs.iters_afterbias = 1  # param -O
            else:
                segmentation.inputs.bias_iters = 4  # param -I
            workflow.connect(ref_deskull, "out_file", segmentation, "in_files")
            workflow.connect(
                segmentation, "restored_image", outputnode, "tissue_restored"
            )
        segmentation.long_name = "Reference tissue segmentation"
        workflow.connect(segmentation, "partial_volume_files", outputnode, "tissue_pve")

    return workflow
