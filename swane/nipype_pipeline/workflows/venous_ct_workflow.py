from nipype.interfaces.fsl import (
    ApplyMask,
    BinaryMaths,
    ImageMaths,
    RobustFOV,
)
from swane.nipype_pipeline.nodes.ImageStatistics import ImageStatistics
from nipype import Node, IdentityInterface, MapNode
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.SumMultiVols import SumMultiVols
from swane.nipype_pipeline.nodes.SegmentEndocranium import SegmentEndocranium
from configparser import SectionProxy

from swane.config.config_enums import CoreLimit, RegistrationEngine
from swane.nipype_pipeline.nodes.utils import (
    apply_registration_node,
    get_registration_node,
    resolve_registration_engine,
)


def venous_ct_workflow(
    name: str,
    venous_ct_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    venous2_ct_dir: list,
    slicer_path: str,
    base_dir: str = "/",
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    test_run: bool = False,
) -> CustomWorkflow:
    """
    Analysis of CT angiography to obtain in skull veins
    in reference space, scaled in 0-100 value.

    Parameters
    ----------
    name : str
        The workflow name.
    venous_ct_dir : path
        The directory path of the no contrast scan DICOM files.
    config: SectionProxy
        workflow settings.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings (drives the registration engine).
    venous2_ct_dir : list
        A list of directory paths of the contrast scans DICOM files.
    slicer_path: path
        Path to 3D Slicer executable
    base_dir : str, optional
        The base directory path relative to parent workflow. The default is "/".
    max_cpu : int, optional
        If greater than 0, limit the core usage of the registration tools. The
        default is 0.
    multicore_node_limit : CoreLimit, optional
        Preference for the registration tools core usage. The default is
        CoreLimit.SOFT_CAP.
    test_run : bool, optional
        If True, speed up the endocranium segmentation for prerelease test
        runs at the cost of accuracy. These parameters don't change the
        workflow graph, so they are overridden unconditionally (even over an
        explicit user value). The default is False.

    Input Node Fields
    ----------
    reference : path
        T13D.
    reference_brain : path
        Betted T13D.

    Returns
    -------
    workflow : CustomWorkflow
        The venous workflow.

    Output Node Fields
    ----------
    veins : path
        Intracranial veins in T13D reference space.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # CT follows the global registration engine (ANTs by default). The former
    # scientific FSL pin (``# FLIRT performs better on CT``) is lifted so CT
    # exercises ANTs, and the comparative oracle validates it on real data.
    # SynthMorph is the known-worse backend on CT, so an explicit SynthMorph
    # choice falls back to FSL; an ANTs config stays ANTs (that is the point of
    # this work), and an explicit FSL choice stays FSL.
    engine = resolve_registration_engine(synth_config, allow_ants=True)
    if engine == RegistrationEngine.SYNTH:
        engine = RegistrationEngine.FSL

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference_brain", "reference"]), name="inputnode"
    )

    # Output Node
    outputnode = Node(IdentityInterface(fields=["veins", "basal"]), name="outputnode")

    # NODE 1: Conversion dicom -> nifti
    veins_conv = Node(CustomDcm2niix(), name="veins_ct_conv")
    veins_conv.long_name = "Non-contrast scan %s"
    veins_conv.inputs.source_dir = venous_ct_dir
    veins_conv.inputs.bids_format = False
    veins_conv.inputs.out_filename = "veins"
    veins_conv.inputs.name_conflicts = 1
    veins_conv.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    veins_reOrient = Node(ForceOrient(), name="veins_ct_reOrient")
    veins_reOrient.long_name = "Non-contrast scan %s"
    workflow.connect(veins_conv, "converted_files", veins_reOrient, "in_file")

    # NODE 3: Crop neck
    veins_robustfov = Node(RobustFOV(), name="%s_robustfov" % name)
    veins_robustfov.long_name = "Non-contrast scan %s"
    workflow.connect(veins_reOrient, "out_file", veins_robustfov, "in_file")

    # NODE 3: Conversion dicom -> nifti
    veins2_conv = MapNode(
        CustomDcm2niix(),
        name="veins_2conv",
        iterfield=["source_dir"],
    )
    veins2_conv.long_name = "Contrast scans %s"
    veins2_conv.inputs.source_dir = venous2_ct_dir
    veins2_conv.inputs.bids_format = False

    # NODE 4: Orienting in radiological convention
    veins2_reOrient = MapNode(
        ForceOrient(),
        name="veins2_ct_reOrient",
        iterfield=["in_file"],
    )
    veins2_reOrient.long_name = "Contrast scans %s"
    workflow.connect(veins2_conv, "converted_files", veins2_reOrient, "in_file")

    veins2_robustfov = MapNode(
        RobustFOV(),
        name="%s2_robustfov" % name,
        iterfield=["in_file"],
    )
    veins2_robustfov.long_name = "Contrast scans %s"
    workflow.connect(veins2_reOrient, "out_file", veins2_robustfov, "in_file")

    # NODE 5: Scalp removal
    deskull = Node(SegmentEndocranium(), name="segment_endocranium", mem_gb=2.5)
    deskull.long_name = "Non-contrast scan %s"
    deskull.inputs.slicer_cmd = slicer_path
    seg_iterations = config.getint_safe("segment_endocranium_iteration")
    seg_oversampling = config.getfloat_safe("segment_endocranium_oversampling")
    if test_run:
        # SegmentEndocranium's own parameters don't change the workflow
        # graph (same nodes either way), so unlike other test_run knobs we
        # unconditionally override them here, even if the user picked a
        # different value. SWANe defaults (preference_list.py) are tuned
        # above the underlying tool's own baseline for accuracy:
        # iteration=6 vs tool default 2, oversampling=1.5 vs tool default
        # 1.0. Drop to the tool's own baseline.
        seg_iterations = 2
        seg_oversampling = 1.0
    deskull.inputs.iterations = seg_iterations
    deskull.inputs.smoothingKernelSize = config.getfloat_safe(
        "segment_endocranium_kernel"
    )
    deskull.inputs.oversampling = seg_oversampling
    deskull.inputs.skull_threshold = config.getint_safe("skull_threshold")
    workflow.connect(veins_robustfov, "out_roi", deskull, "in_file")

    # NODE 6: Mask in radiological convention
    veins_mask_reOrient = Node(ForceOrient(), name="veins_mask_reOrient")
    veins_mask_reOrient.long_name = "Inskull mask %s"
    workflow.connect(deskull, "out_file", veins_mask_reOrient, "in_file")

    # NODE 7: Linear registration of veins to reference space
    basal_2_ref = get_registration_node(
        name="veins_ct_2_ref",
        name_prefix="Non-contrast scan",
        name_suffix="to reference space",
        engine=engine,
        workflow=workflow,
        moving=[veins_robustfov, "out_roi"],
        reference=[inputnode, "reference"],
        non_linear=False,
        is_volumetric=True,
        flirt_cost="mutualinfo",
        flirt_search=90,
        test_run=test_run,
        max_cpu=max_cpu,
        multicore_node_limit=multicore_node_limit,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    # The basal scan resampled into reference space.
    workflow.connect(
        basal_2_ref.registered_node,
        basal_2_ref.registered_field,
        outputnode,
        "basal",
    )

    # NODE 8: Linear registration of every contrast scan to the basal veins.
    # map_moving builds the registration as a MapNode iterating the contrast
    # series; its already-registered output (``registered_field``) is what the
    # subtraction consumes, so no separate apply node is needed.
    contrast_2_basal = get_registration_node(
        name="veins_ct_2_contrast",
        name_prefix="Contrast scan",
        name_suffix="to non-contrast scan",
        engine=engine,
        workflow=workflow,
        moving=[veins2_robustfov, "out_roi"],
        reference=[veins_robustfov, "out_roi"],
        non_linear=False,
        is_volumetric=True,
        flirt_cost="mutualinfo",
        flirt_search=90,
        map_moving=True,
        test_run=test_run,
        max_cpu=max_cpu,
        multicore_node_limit=multicore_node_limit,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )

    # NODE 9: Subtract basal from contrast scan
    veins_subtraction = MapNode(
        BinaryMaths(),
        name="veins_ct_subtraction",
        iterfield=["in_file"],
    )
    veins_subtraction.long_name = "Subtract non-contrast scan"
    veins_subtraction.inputs.operation = "sub"
    workflow.connect(
        contrast_2_basal.registered_node,
        contrast_2_basal.registered_field,
        veins_subtraction,
        "in_file",
    )
    workflow.connect(veins_robustfov, "out_roi", veins_subtraction, "operand_file")

    # NODE 10: Sum all contrasts
    veins_sum = Node(SumMultiVols(), name="veins_ct_sum")
    veins_sum.long_name = "Sum contrast scans"
    veins_sum.inputs.out_file = "vein_contrast_sum.nii.gz"
    workflow.connect(veins_subtraction, "out_file", veins_sum, "vol_files")
    workflow.connect(veins_subtraction, "out_file", outputnode, "contrast")

    # NODE 11: Apply brain mask
    veins_inskull_mask = Node(ApplyMask(), name="veins_ct_mask")
    veins_inskull_mask.long_name = "%s inskull veins"
    workflow.connect(veins_sum, "out_file", veins_inskull_mask, "in_file")
    workflow.connect(veins_mask_reOrient, "out_file", veins_inskull_mask, "mask_file")

    # NODE 12: Get the max value of venous phase
    veins_range = Node(ImageStatistics(), name="veins_ct_range")
    veins_range.long_name = "intensity range detection"
    workflow.connect(veins_inskull_mask, "out_file", veins_range, "in_file")

    # NODE 13: Venous phase rescaling in 0-100
    veins_rescale = Node(ImageMaths(), name="veins_ct_rescale")
    veins_rescale.long_name = "intensity normalization"

    # Function to define the operation string
    def rescale_string(max_value):
        op_string = "-mul 100 -div %f" % max_value
        return op_string

    workflow.connect(
        veins_range, ("max_value", rescale_string), veins_rescale, "op_string"
    )
    workflow.connect(veins_inskull_mask, "out_file", veins_rescale, "in_file")

    # NODE 14: Bring the rescaled veins into reference space, reusing the basal
    # reference registration. registration=basal_2_ref is mandatory on the ANTs
    # branch so the reused linear transform is applied through wire_transforms
    # (correct which_to_invert), not the composed-boundary single-field path.
    veins_2_ref = apply_registration_node(
        name="veins",
        name_prefix="Rescaled veins",
        name_suffix="to reference space",
        engine=engine,
        workflow=workflow,
        warp=[basal_2_ref.out_registered_node, basal_2_ref.warp],
        registration=basal_2_ref,
        moving=[veins_rescale, "out_file"],
        reference=[inputnode, "reference_brain"],
        out_file="r-veins_ct_inskull.nii.gz",
        non_linear=False,
    )

    workflow.connect(veins_2_ref, "out_file", outputnode, "veins")

    return workflow
