from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient

from nipype.interfaces.fsl import BET
from nipype.interfaces.utility import IdentityInterface

from nipype import Node

def ref_workflow(name: str, dicom_dir: str, base_dir: str = "/") -> CustomWorkflow:
    """
    T13D workflow to use as reference.

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The file path of the DICOM files.
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
    ref_conv.inputs.out_filename = "ref"

    # NODE 2: Orienting in radiological convention
    ref_reOrient = Node(ForceOrient(), name='%s_reOrient' % name)
    workflow.connect(ref_conv, "converted_files", ref_reOrient, "in_file")

    # NODE 3: Scalp removal
    ref_BET = Node(BET(), name='ref_BET')
    ref_BET.inputs.frac = 0.5
    ref_BET.inputs.mask = True
    ref_BET.inputs.robust = True
    ref_BET.inputs.threshold = True
    workflow.connect(ref_reOrient, "out_file", ref_BET, "in_file")
    
    workflow.connect(ref_reOrient, "out_file", outputnode, "ref")
    workflow.connect(ref_BET, "out_file", outputnode, "ref_brain")
    workflow.connect(ref_BET, "mask_file", outputnode, "ref_mask")

    return workflow
