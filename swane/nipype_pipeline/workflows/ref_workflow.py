from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.CropFov import CropFov

from nipype.interfaces.fsl import BET
from nipype.interfaces.utility import IdentityInterface

from nipype import Node


def ref_workflow(name: str, dicom_dir: str, biasCorrectionBet: bool, base_dir: str = "/") -> CustomWorkflow:
    """
    T13D workflow to use as reference.

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The file path of the DICOM files.
    biasCorrectionBet: bool
        If True use -B parameters for bet, otherwise use -R
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    -

    Returns
    -------
    workflow : CustomWorkflow
        The T13D reference workflow.
        
    Output Node Fields
    ----------
    ref : path
        T13D.
    ref_brain : path
        Betted T13D.
    ref_mask : path
        Brain mask from T13D bet command.

    """
    
    workflow = CustomWorkflow(name=name, base_dir=base_dir)
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['ref', 'ref_brain', 'ref_mask']),
        name='outputnode')

    # NODE 1: Conversion dicom -> nifti
    ref_conv = Node(CustomDcm2niix(), name='%s_conv' % name)
    ref_conv.inputs.source_dir = dicom_dir
    ref_conv.inputs.crop = True
    ref_conv.inputs.bids_format = False
    ref_conv.inputs.out_filename = "converted"

    # NODE 2: Orienting in radiological convention
    ref_reOrient = Node(ForceOrient(), name='%s_reOrient' % name)
    workflow.connect(ref_conv, "converted_files", ref_reOrient, "in_file")

    # NODE 3: Crop FOV larger than 256mm for subsequent freesurfer
    ref_reScale = Node(CropFov(), name='%s_reScale' % name)
    ref_reScale.long_name = "Crop large FOV"
    ref_reScale.inputs.max_dim = 256
    ref_reScale.inputs.out_file = "ref"
    workflow.connect(ref_reOrient, "out_file", ref_reScale, "in_file")

    # NODE 4: Scalp removal
    ref_BET = Node(BET(), name='ref_BET')
    ref_BET.inputs.frac = 0.3
    ref_BET.inputs.mask = True
    if biasCorrectionBet:
        ref_BET.inputs.reduce_bias = True
    else:
        ref_BET.inputs.robust = True

    workflow.connect(ref_reScale, "out_file", ref_BET, "in_file")
    
    workflow.connect(ref_reScale, "out_file", outputnode, "ref")
    workflow.connect(ref_BET, "out_file", outputnode, "ref_brain")
    workflow.connect(ref_BET, "mask_file", outputnode, "ref_mask")

    return workflow
