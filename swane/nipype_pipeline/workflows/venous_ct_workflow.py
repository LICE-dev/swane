from nipype.interfaces.fsl import (
    BET,
    FLIRT,
    ApplyMask,
    ImageStats,
    BinaryMaths,
    ImageMaths,
    ApplyXFM,
)
from nipype import Node, IdentityInterface, MapNode
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.SynthMorphReg import SynthMorphReg
from swane.nipype_pipeline.nodes.SynthMorphApply import SynthMorphApply
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from swane.nipype_pipeline.nodes.SumMultiVols import SumMultiVols
from swane.nipype_pipeline.nodes.SegmentEndocranium2 import SegmentEndocranium
from configparser import SectionProxy
from swane.utils.DependencyManager import DependencyManager

def venous_ct_workflow(
    name: str,
    venous_ct_dir: str,
    config: SectionProxy,
    venous2_ct_dir: list,
    slicer_path: str,
    base_dir: str = "/",
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
    venous2_ct_dir : list
        A list of directory paths of the contrast scans DICOM files.
    slicer_path: path
        Path to 3D Slicer executable
    base_dir : str, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    ref : path
        T13D.
    ref_brain : path
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

    # Input Node
    inputnode = Node(IdentityInterface(fields=["ref_brain", "ref"]), name="inputnode")

    # Output Node
    outputnode = Node(IdentityInterface(fields=["veins","debug"]), name="outputnode")

    # NODE 1: Conversion dicom -> nifti
    veins_conv = Node(CustomDcm2niix(), name="veins_ct_conv")
    veins_conv.inputs.source_dir = venous_ct_dir
    veins_conv.inputs.bids_format = False
    veins_conv.inputs.out_filename = "veins"
    veins_conv.inputs.name_conflicts = 1
    veins_conv.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    veins_reOrient = Node(ForceOrient(), name="veins_ct_reOrient")
    workflow.connect(veins_conv, "converted_files", veins_reOrient, "in_file")

    # NODE 3: Conversion dicom -> nifti
    veins2_conv = MapNode(
        CustomDcm2niix(),
        name="veins_2conv",
        iterfield=["source_dir"],
    )
    veins2_conv.inputs.source_dir = venous2_ct_dir
    veins2_conv.inputs.bids_format = False

    # NODE 4: Orienting in radiological convention
    veins2_reOrient = MapNode(
        ForceOrient(),
        name="veins2_ct_reOrient",
        iterfield=["in_file"],
    )
    workflow.connect(veins2_conv, "converted_files", veins2_reOrient, "in_file")

    # NODE 5: Scalp removal
    deskull = Node(SegmentEndocranium(), name="segment_endocranium", mem_gb=2.5)
    deskull.inputs.slicer_cmd = slicer_path
    deskull.inputs.iterations = config.getint_safe("segment_endocranium_iteration")
    deskull.inputs.smoothingKernelSize = config.getfloat_safe("segment_endocranium_kernel")
    deskull.inputs.oversampling = config.getfloat_safe("segment_endocranium_oversampling")
    workflow.connect(veins_reOrient, "out_file", deskull, "in_file")

    # NODE 7: Linear registration of veins to reference space
    if DependencyManager.is_freesurfer_synth():
        basal_2_ref = Node(SynthMorphReg(), name="veins_ct_synthreg", mem_gb=9)
        basal_2_ref.long_name = "%s to reference space"
        basal_2_ref.inputs.model = "affine"
        workflow.connect(veins_reOrient, "out_file", basal_2_ref, "in_file")
        workflow.connect(inputnode, "ref", basal_2_ref, "reference")
    else:
        basal_2_ref = Node(FLIRT(), name="veins_ct_flirt_2_ref")
        basal_2_ref.long_name = "%s to reference space"
        basal_2_ref.inputs.out_matrix_file = "veins2ref.mat"
        basal_2_ref.inputs.cost = "normcorr"
        basal_2_ref.inputs.searchr_x = [-90, 90]
        basal_2_ref.inputs.searchr_y = [-90, 90]
        basal_2_ref.inputs.searchr_z = [-90, 90]
        basal_2_ref.inputs.dof = 6
        basal_2_ref.inputs.interp = "trilinear"
        workflow.connect(veins_reOrient, "out_file", basal_2_ref, "in_file")
        workflow.connect(inputnode, "ref", basal_2_ref, "reference")

    # NODE 8: Linear registration of contrast to basal veins
    contrast_2_basal = MapNode(
        FLIRT(),
        name="veins_ct_flirt_2_contrast",
        iterfield=["in_file"],
    )
    contrast_2_basal.long_name = "%s to basal scan"
    contrast_2_basal.inputs.out_matrix_file = "veins2ref.mat"
    contrast_2_basal.inputs.cost = "mutualinfo"
    contrast_2_basal.inputs.searchr_x = [-90, 90]
    contrast_2_basal.inputs.searchr_y = [-90, 90]
    contrast_2_basal.inputs.searchr_z = [-90, 90]
    contrast_2_basal.inputs.dof = 6
    contrast_2_basal.inputs.interp = "trilinear"
    workflow.connect(veins2_reOrient, "out_file", contrast_2_basal, "in_file")
    workflow.connect(veins_reOrient, "out_file", contrast_2_basal, "reference")

    # NODE 9: Subtract basal from contrast scan
    veins_subtraction = MapNode(
        BinaryMaths(),
        name="veins_ct_subtraction",
        iterfield=["in_file"],
    )
    veins_subtraction.long_name = "Subtract basal scan"
    veins_subtraction.inputs.operation = "sub"
    workflow.connect(contrast_2_basal, "out_file", veins_subtraction, "in_file")
    workflow.connect(veins_reOrient, "out_file", veins_subtraction, "operand_file")

    # NODE 10: Sum all contrasts
    veins_sum = Node(SumMultiVols(), name="veins_ct_sum")
    veins_sum.long_name = "Sum contrast scans"
    veins_sum.inputs.out_file = "test.nii.gz"
    workflow.connect(veins_subtraction, "out_file", veins_sum, "vol_files")

    # NODE 11: Apply brain mask
    veins_inskull_mask = Node(ApplyMask(), name="veins_ct_mask")
    veins_inskull_mask.long_name = "%s inskull veins"
    workflow.connect(veins_sum, "out_file", veins_inskull_mask, "in_file")
    workflow.connect(deskull, "out_file", veins_inskull_mask, "mask_file")

    # NODE 12: Get the max value of venous phase
    veins_range = Node(ImageStats(), name="veins_ct_range")
    veins_range.long_name = "intensity range detection"
    veins_range.inputs.op_string = "-R"
    workflow.connect(veins_inskull_mask, "out_file", veins_range, "in_file")

    # NODE 13: Venous phase rescaling in 0-100
    veins_rescale = Node(ImageMaths(), name="veins_ct_rescale")
    veins_rescale.long_name = "intensity normalization"

    # Function to define the operation string
    def rescale_string(intensity_range):
        op_string = "-mul 100 -div %f" % intensity_range[1]
        return op_string

    workflow.connect(
        veins_range, ("out_stat", rescale_string), veins_rescale, "op_string"
    )
    workflow.connect(veins_inskull_mask, "out_file", veins_rescale, "in_file")

    if DependencyManager.is_freesurfer_synth():
        veins_2_ref = Node(SynthMorphApply(), name="veins_synthapply")
        veins_2_ref.long_name = "%s in reference space"
        veins_2_ref.inputs.out_file = "r-veins_inskull.nii.gz"
        workflow.connect(veins_rescale, "out_file", veins_2_ref, "in_file")
        workflow.connect(basal_2_ref, "warp_file", veins_2_ref, "warp_file")
    else:
        veins_2_ref = Node(ApplyXFM(), name="veins_flirt")
        veins_2_ref.long_name = "%s to reference space"
        veins_2_ref.inputs.out_file = "r-veins_inskull.nii.gz"
        veins_2_ref.inputs.interp = "trilinear"
        workflow.connect(veins_rescale, "out_file", veins_2_ref, "in_file")
        workflow.connect(basal_2_ref, "out_matrix_file", veins_2_ref, "in_matrix_file")
        workflow.connect(inputnode, "ref_brain", veins_2_ref, "reference")

    workflow.connect(veins_2_ref, "out_file", outputnode, "veins")

    return workflow
