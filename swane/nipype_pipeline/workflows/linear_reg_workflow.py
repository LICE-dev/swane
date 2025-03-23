from nipype.interfaces.fsl import (BET, FLIRT, RobustFOV, ApplyXFM, ApplyMask)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from nipype import Node
from nipype.interfaces.utility import IdentityInterface
from configparser import SectionProxy


def linear_reg_workflow(name: str, dicom_dir: str, config: SectionProxy, base_dir: str = "/", is_volumetric: bool = True, is_partial_coverage : bool = False) -> CustomWorkflow:
    """
    Transforms input images in a reference space through a linear registration.

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
    is_volumetric : bool, optional
        True if input is 3D. The default is True.
    is_partial_coverage : bool, optional
        True if series only includes brain partially. The default is False.

    Input Node Fields
    ----------
    reference : path
        The reference image for the registration.
    output_name : str
        The name for registered file.
    brain_mask : path
        The brain mask image. Only needed if is_partial_coverage is True.

    Returns
    -------
    workflow : CustomWorkflow
        The linear registration workflow.
        
    Output Node Fields
    ----------
    registered_file : string
        Output file in T13D reference space.
    betted_registered_file : string
        Output betted file in T13D reference space.
    out_matrix_file : path
        Linear registration matrix to T13D reference space.

    """
    
    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=['reference', 'output_name', 'brain_mask']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['registered_file', 'betted_registered_file' 'out_matrix_file']),
        name='outputnode')

    # NODE 1: Conversion dicom -> nifti
    conversion = Node(CustomDcm2niix(), name='%s_conv' % name)
    conversion.inputs.source_dir = dicom_dir
    conversion.inputs.bids_format = False
    conversion.inputs.out_filename = name
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    reorient = Node(ForceOrient(), name='%s_reorient' % name)
    workflow.connect(conversion, "converted_files", reorient, "in_file")

    # NODE 3: Crop neck
    robustfov = Node(RobustFOV(), name="%s_robustfov" % name)
    workflow.connect(reorient, "out_file", robustfov, "in_file")

    def get_betted_name(basename):
        return 'r-%s_brain.nii.gz' % basename

    def get_unbetted_name(basename):
        return 'r-%s.nii.gz' % basename

    if is_partial_coverage:
        # NODE 4a: Linear registration to reference space
        flirt_2_ref = Node(FLIRT(), name='%s_2_ref' % name)
        flirt_2_ref.long_name = "%s to reference space"
        flirt_2_ref.inputs.out_matrix_file = "%s_2_ref.mat" % name

        flirt_2_ref.inputs.cost = "mutualinfo"
        flirt_2_ref.inputs.searchr_x = [-40, 40]
        flirt_2_ref.inputs.searchr_y = [-40, 40]
        flirt_2_ref.inputs.searchr_z = [-40, 40]
        flirt_2_ref.inputs.dof = 6
        flirt_2_ref.inputs.interp = "trilinear"

        workflow.connect(robustfov, "out_roi", flirt_2_ref, "in_file")
        workflow.connect(inputnode, ("output_name", get_unbetted_name), flirt_2_ref, "out_file")
        workflow.connect(inputnode, "reference", flirt_2_ref, "reference")

        # NODE 5a: Apply brain mask
        brain_masking = Node(ApplyMask(), name='%s_brain_mask' % name)
        brain_masking.long_name = "Brain %s"
        workflow.connect(flirt_2_ref, "out_file", brain_masking, "in_file")
        workflow.connect(inputnode, ("output_name", get_betted_name), brain_masking, "out_file")
        workflow.connect(inputnode, "brain_mask", brain_masking, "mask_file")

        workflow.connect(flirt_2_ref, "out_file", outputnode, "registered_file")
        workflow.connect(brain_masking, "out_file", outputnode, "betted_registered_file")
        workflow.connect(flirt_2_ref, "out_matrix_file", outputnode, "out_matrix_file")

    else:
        # NODE 4b: Scalp removal
        bet = Node(BET(), '%s_BET' % name)
        if config is not None:
            bet.inputs.frac = config.getfloat_safe('bet_thr')
        if config is not None and config.getboolean_safe('bet_bias_correction'):
            bet.inputs.reduce_bias = True
        else:
            bet.inputs.robust = True
        bet.inputs.mask = True
        workflow.connect(robustfov, "out_roi", bet, "in_file")

        # NODE 5b: Linear registration to reference space
        flirt_2_ref = Node(FLIRT(), name='%s_brain_2_ref' % name)
        flirt_2_ref.long_name = "%s to reference space"
        flirt_2_ref.inputs.out_matrix_file = "%s_2_ref.mat" % name

        if is_volumetric:
            flirt_2_ref.inputs.cost = "mutualinfo"
            flirt_2_ref.inputs.searchr_x = [-90, 90]
            flirt_2_ref.inputs.searchr_y = [-90, 90]
            flirt_2_ref.inputs.searchr_z = [-90, 90]
            flirt_2_ref.inputs.dof = 6
            flirt_2_ref.inputs.interp = "trilinear"

        workflow.connect(bet, "out_file", flirt_2_ref, "in_file")
        workflow.connect(inputnode, ("output_name", get_betted_name), flirt_2_ref, "out_file")
        workflow.connect(inputnode, "reference", flirt_2_ref, "reference")

        # NODE 6b: Linear trasformation of unbetted series to reference space
        unbet_flirt = Node(ApplyXFM(), name='%s_2_ref' % name)
        unbet_flirt.long_name = "%s to reference space"

        if is_volumetric:
            unbet_flirt.inputs.cost = "mutualinfo"
            unbet_flirt.inputs.searchr_x = [-90, 90]
            unbet_flirt.inputs.searchr_y = [-90, 90]
            unbet_flirt.inputs.searchr_z = [-90, 90]
            unbet_flirt.inputs.dof = 6
            unbet_flirt.inputs.interp = "trilinear"

        workflow.connect(robustfov, "out_roi", unbet_flirt, "in_file")
        workflow.connect(flirt_2_ref, "out_matrix_file", unbet_flirt, "in_matrix_file")
        workflow.connect(inputnode, ("output_name", get_unbetted_name), unbet_flirt, "out_file")
        workflow.connect(inputnode, "reference", unbet_flirt, "reference")


        workflow.connect(flirt_2_ref, "out_file", outputnode, "betted_registered_file")
        workflow.connect(unbet_flirt, "out_file", outputnode, "registered_file")
        workflow.connect(flirt_2_ref, "out_matrix_file", outputnode, "out_matrix_file")
    
    return workflow
