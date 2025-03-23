from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.CropFov import CropFov
from configparser import SectionProxy
from swane.utils.DataInputList import DataInputList
from nipype.interfaces.fsl import BET, RobustFOV
from nipype.interfaces.utility import IdentityInterface

from nipype import Node


def ref_workflow(name: str, dicom_dir: str, config: SectionProxy, base_dir: str = "/") -> CustomWorkflow:
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
    conversion = Node(CustomDcm2niix(), name='%s_conv' % name)
    conversion.inputs.source_dir = dicom_dir
    conversion.inputs.bids_format = False
    conversion.inputs.out_filename = "converted"
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    ref_reOrient = Node(ForceOrient(), name='%s_reOrient' % name)
    workflow.connect(conversion, "converted_files", ref_reOrient, "in_file")

    # NODE 3: Crop neck
    ref_robustfov = Node(RobustFOV(), name= "%s_robustfov" % name)
    ref_robustfov.inputs.out_roi = "ref_robustfov.nii.gz"
    workflow.connect(ref_reOrient, "out_file", ref_robustfov, "in_file")

    # NODE 4: Crop FOV larger than 256mm for subsequent freesurfer
    ref_reScale = Node(CropFov(), name='%s_reScale' % name)
    ref_reScale.long_name = "Crop large FOV"
    ref_reScale.inputs.max_dim = 256
    ref_reScale.inputs.out_file = "ref.nii.gz"
    workflow.connect(ref_robustfov, "out_roi", ref_reScale, "in_file")

    # NODE 5: Scalp removal
    ref_BET = Node(BET(), name='%s_BET' % name)
    ref_BET.inputs.mask = True
    ref_BET.inputs.frac = config.getfloat_safe('bet_thr')
    if config.getboolean_safe('bet_bias_correction'):
        ref_BET.inputs.reduce_bias = True
    else:
        ref_BET.inputs.robust = True

    workflow.connect(ref_reScale, "out_file", ref_BET, "in_file")
    
    workflow.connect(ref_reScale, "out_file", outputnode, "ref")
    workflow.connect(ref_BET, "out_file", outputnode, "ref_brain")
    workflow.connect(ref_BET, "mask_file", outputnode, "ref_mask")

    return workflow
