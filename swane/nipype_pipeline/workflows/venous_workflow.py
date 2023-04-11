from nipype.interfaces.fsl import (BET, FLIRT, Split, ApplyMask, ImageStats, ImageMaths, ApplyXFM)
from nipype.interfaces.utility import Merge
from nipype.pipeline.engine import Node

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.VenousCheck import VenousCheck

from nipype.interfaces.utility import IdentityInterface


def venous_workflow(name: str, venous_dir: str, venous2_dir: str = None, base_dir: str = "/") -> CustomWorkflow:
    """
    Analysis of phase contrasts images (in single or two series) to obtain in skull veins
    in reference space, scaled in 0-100 value.

    Parameters
    ----------
    name : str
        The workflow name.
    venous_dir : path
        The directory path of the venous phase contrast DICOM files.
    venous2_dir : path
        If veins phase is divided from anatomic phase, use this param to load the second DICOM files directory.
    base_dir : str, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
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
    inputnode = Node(
        IdentityInterface(fields=['ref_brain']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['veins']),
        name='outputnode')

    # NODE 1a: Conversion dicom -> nifti
    veins_conv = Node(CustomDcm2niix(), name='veins_conv')
    veins_conv.inputs.source_dir = venous_dir
    veins_conv.inputs.bids_format = False
    veins_conv.inputs.out_filename = "veins"

    # NODE 2a: Orienting in radiological convention
    veins_reOrient = Node(ForceOrient(), name='veins_reOrient')
    workflow.connect(veins_conv, "converted_files", veins_reOrient, "in_file")

    # NODE 4: Detect the venous phase from the anatomic phase
    veins_check = Node(VenousCheck(), name='veins_check')
    veins_check.long_name = "angiographic phase detection"

    # If the phases are in the same sequence
    if venous2_dir is None:
        # NODE 3a: Divide the two phases from the phase contrast
        veins_split = Node(Split(), name='veins_split')
        veins_split.long_name = "phase splitting"
        veins_split.inputs.dimension = 't'
        workflow.connect(veins_reOrient, "out_file", veins_split, "in_file")

        workflow.connect(veins_split, "out_files", veins_check, "in_files")
    else:
        # NODE 1b: Conversion dicom -> nifti
        veins2_conv = Node(CustomDcm2niix(), name='veins2_conv')
        veins2_conv.inputs.source_dir = venous2_dir
        veins2_conv.inputs.bids_format = False
        veins2_conv.inputs.out_filename = "veins2"

        # NODE 2b: Orienting in radiological convention
        veins2_reOrient = Node(ForceOrient(), name='veins2_reOrient')
        workflow.connect(veins2_conv, "converted_files", veins2_reOrient, "in_file")

        # NODE 3b: Merge the two phases
        veins_merge = Node(Merge(2), name="veins_merge")
        veins_merge.long_name = "phase merging"
        workflow.connect(veins_reOrient, "out_file", veins_merge, "in1")
        workflow.connect(veins2_reOrient, "out_file", veins_merge, "in2")

        workflow.connect(veins_merge, "out", veins_check, "in_files")

    # NODE 5: Scalp removal and in skull structures segmentation
    bet = Node(BET(), name='veins_bet')
    bet.inputs.frac = 0.4
    bet.inputs.mask = True
    bet.inputs.threshold = True
    bet.inputs.surfaces = True
    workflow.connect(veins_check, "out_file_anat", bet, "in_file")

    # NODE 6: Linear registration of anatomic phase to reference space
    anat_flirt = Node(FLIRT(), name='anat_flirt')
    anat_flirt.long_name = "%s to reference space"
    anat_flirt.inputs.out_matrix_file = "veins2ref.mat"
    anat_flirt.inputs.cost = "mutualinfo"
    anat_flirt.inputs.searchr_x = [-90, 90]
    anat_flirt.inputs.searchr_y = [-90, 90]
    anat_flirt.inputs.searchr_z = [-90, 90]
    anat_flirt.inputs.dof = 6
    anat_flirt.inputs.interp = "trilinear"
    workflow.connect(bet, "out_file", anat_flirt, "in_file")
    workflow.connect(inputnode, "ref_brain", anat_flirt, "reference")

    # NODE 7: Apply in skull mask to venous phase
    veins_inskull_mask = Node(ApplyMask(), name='veins_inskull_mask')
    veins_inskull_mask.long_name = "%s inskull veins"
    workflow.connect(veins_check, "out_file_veins", veins_inskull_mask, "in_file")
    workflow.connect(bet, "inskull_mask_file", veins_inskull_mask, "mask_file")

    # NODE 8: Linear transformation of in skull venous phase in reference space
    veins_flirt = Node(ApplyXFM(), name='veins_flirt')
    veins_flirt.long_name = "%s to reference space"
    veins_flirt.inputs.out_file = "r-veins_inskull.nii.gz"
    veins_flirt.inputs.interp = "trilinear"
    workflow.connect(veins_inskull_mask, "out_file", veins_flirt, "in_file")
    workflow.connect(anat_flirt, "out_matrix_file", veins_flirt, "in_matrix_file")
    workflow.connect(inputnode, "ref_brain", veins_flirt, "reference")

    # NODE 9: Get the max value of venous phase
    veins_range = Node(ImageStats(), name="veins_range")
    veins_range.long_name = "intensity range detection"
    veins_range.inputs.op_string = "-R"
    workflow.connect(veins_flirt, "out_file", veins_range, "in_file")

    # NODE 10: Venous phase rescaling in 0-100
    veins_rescale = Node(ImageMaths(), name="veins_rescale")
    veins_rescale.long_name = "intensity normalization"
    veins_rescale.inputs.out_file = "r-veins_inskull.nii.gz"
    
    # Function to define the operation string
    def rescale_string(range):
        op_string = "-mul 100 -div %f" % range[1]
        return op_string

    workflow.connect(veins_range, ('out_stat', rescale_string), veins_rescale, 'op_string')
    workflow.connect(veins_flirt, "out_file", veins_rescale, "in_file")

    workflow.connect(veins_rescale, "out_file", outputnode, "veins")

    return workflow
