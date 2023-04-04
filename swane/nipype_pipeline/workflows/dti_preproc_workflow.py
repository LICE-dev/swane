from nipype.interfaces.fsl import (BET, FLIRT, ConvertXFM, ExtractROI, EddyCorrect, DTIFit, ApplyXFM, FNIRT)
from nipype.pipeline.engine import Node
import os

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.CustomBEDPOSTX5 import CustomBEDPOSTX5

from nipype.interfaces.utility import IdentityInterface


def dti_preproc_workflow(name: str, dti_dir: str, mni_dir: str = None, base_dir: str = "/", is_tractography: bool = False) -> CustomWorkflow:
    """
    DTI preprocessing workflow with eddy current and motion artifact correction.
    Diffusion metrics calculation and, if needed, bayesian estimation of
    diffusion parameters.

    Parameters
    ----------
    name : str
        The workflow name.
    dti_dir : path
        The directory path of DTI dicom files.
    mni_dir : path, optional
        The file path of the MNI template. The default is None.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    is_tractography : bool, optional
        Enable bayesian estimation of diffusion parameters. The default is False.
        
    Input Node Fields
    ----------
    ref_brain : path
        Betted T13D reference file.

    Returns
    -------
    workflow : CustomWorkflow
        The DTI preprocessing workflow.
        
    Output Node Fields
    ----------
    nodiff_mask_file : path
        Brain mask from b0.
    FA : path
        Fractional anysotropy map in reference space.
    fsamples : path
        Samples from the distribution of anysotropic volume fraction.
    phsamples : path
        Samples from the distribution on phi.
    thsamples : path
        Samples from the distribution on theta.
    diff2ref_mat : path
        Linear registration matrix from diffusion to T13D reference space.
    ref2diff_mat : path
        Linear registration inverse matrix from T13D reference to diffusion space.
    mni2ref_warp : path
        Nonlinear registration warp from MNI atlas to T13D reference space.

    """
    
    workflow = CustomWorkflow(name=name, base_dir=base_dir)
    
    # Input Node
    inputnode = Node(
        IdentityInterface(fields=['ref_brain']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['nodiff_mask_file', 'FA', 'fsamples', 'phsamples',
                                  'thsamples', 'diff2ref_mat', "ref2diff_mat", "mni2ref_warp",
                                  ]),
        name='outputnode')

    # NODE 1: Conversion dicom -> nifti
    conv = Node(CustomDcm2niix(), name='dti_conv')
    conv.inputs.source_dir = dti_dir
    conv.inputs.out_filename = "dti"
    conv.inputs.bids_format = False

    # NODE 1b: Orienting in radiological convention
    reorient = Node(ForceOrient(), name='dti_reOrient')
    workflow.connect(conv, "converted_files", reorient, "in_file")

    # NODE 2: b0 image extraction
    nodif = Node(ExtractROI(), name='dti_nodif')
    nodif.long_name = "b0 extraction"
    nodif.inputs.t_min = 0
    nodif.inputs.t_size = 1
    nodif.inputs.roi_file = 'nodif.nii.gz'
    workflow.connect(reorient, "out_file", nodif, "in_file")

    # NODE 3: Scalp removal from b0 image
    bet = Node(BET(), name='nodif_BET')
    bet.inputs.frac = 0.3
    bet.inputs.robust = True
    bet.inputs.threshold = True
    bet.inputs.mask = True
    workflow.connect(nodif, "roi_file", bet, "in_file")

    # NODE 4: Eddy current and motion artifact correction
    eddy = Node(EddyCorrect(), name='dti_eddy')
    eddy.inputs.ref_num = 0
    eddy.inputs.out_file = "data.nii.gz"
    workflow.connect(reorient, "out_file", eddy, "in_file")

    # NODE 5: DTI metrics calculation
    dtifit = Node(DTIFit(), name='dti_dtifit')
    dtifit.long_name = "DTI metrics calculation"
    workflow.connect(eddy, "eddy_corrected", dtifit, "dwi")
    workflow.connect(bet, "mask_file", dtifit, "mask")
    workflow.connect(conv, "bvecs", dtifit, "bvecs")
    workflow.connect(conv, "bvals", dtifit, "bvals")

    # NODE 6: b0 image linear registration in reference space
    flirt = Node(FLIRT(), name='diff2ref_FLIRT')
    flirt.long_name = "%s to reference space"
    flirt.inputs.out_matrix_file = "diff2ref.mat"
    flirt.inputs.cost = "corratio"
    flirt.inputs.searchr_x = [-90, 90]
    flirt.inputs.searchr_y = [-90, 90]
    flirt.inputs.searchr_z = [-90, 90]
    flirt.inputs.dof = 6
    workflow.connect(bet, "out_file", flirt, "in_file")
    workflow.connect(inputnode, "ref_brain", flirt, "reference")

    # NODE 7: FA linear transformation in reference space
    fa_2_ref_flirt = Node(ApplyXFM(), name='FA2ref_FLIRT')
    fa_2_ref_flirt.inputs.out_file = "r-FA.nii.gz"
    fa_2_ref_flirt.inputs.interp = "trilinear"
    workflow.connect(dtifit, "FA", fa_2_ref_flirt, "in_file")
    workflow.connect(flirt, "out_matrix_file", fa_2_ref_flirt, "in_matrix_file")
    workflow.connect(inputnode, "ref_brain", fa_2_ref_flirt, "reference")
    
    workflow.connect(fa_2_ref_flirt, 'out_file', outputnode, 'FA')

    if is_tractography:
        # NODE 1: Linear registration
        mni_2_ref_flirt = Node(FLIRT(), name='mni_2_ref_flirt')
        mni_2_ref_flirt.long_name = "atlas %s to diffusion space"
        mni_2_ref_flirt.inputs.searchr_x = [-90, 90]
        mni_2_ref_flirt.inputs.searchr_y = [-90, 90]
        mni_2_ref_flirt.inputs.searchr_z = [-90, 90]
        mni_2_ref_flirt.inputs.dof = 12
        mni_2_ref_flirt.inputs.cost = "corratio"
        mni_2_ref_flirt.inputs.out_matrix_file = "mni_2_ref.mat"
        mni_2_ref_flirt.inputs.in_file = mni_dir
        workflow.add_nodes([mni_2_ref_flirt])
        workflow.connect(inputnode, 'ref_brain', mni_2_ref_flirt, 'reference')

        # NODE 2: Nonlinear registration
        mni_2_ref_fnirt = Node(FNIRT(), name='mni_2_ref_fnirt', mem_gb=7)
        mni_2_ref_fnirt.long_name = "atlas %s to diffusion space"
        mni_2_ref_fnirt.inputs.fieldcoeff_file = True
        mni_2_ref_fnirt.inputs.in_file = mni_dir
        workflow.connect(mni_2_ref_flirt, "out_matrix_file", mni_2_ref_fnirt, "affine_file")
        workflow.connect(inputnode, 'ref_brain', mni_2_ref_fnirt, 'ref_file')

        # NODE 8: Bayesian estimation of diffusion parameters
        bedpostx = Node(CustomBEDPOSTX5(), name='dti_bedpostx')
        bedpostx.inputs.n_fibres = 2
        bedpostx.inputs.rician = True
        bedpostx.inputs.sample_every = 25
        bedpostx.inputs.n_jumps = 1250
        bedpostx.inputs.burn_in = 1000
        workflow.connect(eddy, "eddy_corrected", bedpostx, "dwi")
        workflow.connect(bet, "mask_file", bedpostx, "mask")
        workflow.connect(conv, "bvecs", bedpostx, "bvecs")
        workflow.connect(conv, "bvals", bedpostx, "bvals")

        # NODE 9: Linear transformation inverse matrix calculation from diffusion to reference space
        ref2diff_convert = Node(ConvertXFM(), name='ref2diff_convert')
        ref2diff_convert.long_name = "inverse transformation from reference space"
        ref2diff_convert.inputs.invert_xfm = True
        ref2diff_convert.inputs.out_file = 'ref2diff.mat'
        workflow.connect(flirt, "out_matrix_file", ref2diff_convert, "in_file")

        workflow.connect(bedpostx, "merged_fsamples", outputnode, "fsamples")
        workflow.connect(bet, "mask_file", outputnode, "nodiff_mask_file")
        workflow.connect(bedpostx, "merged_phsamples", outputnode, "phsamples")
        workflow.connect(bedpostx, "merged_thsamples", outputnode, "thsamples")

        workflow.connect(flirt, "out_matrix_file", outputnode, "diff2ref_mat")
        workflow.connect(ref2diff_convert, "out_file", outputnode, "ref2diff_mat")
        workflow.connect(mni_2_ref_fnirt, "fieldcoeff_file", outputnode, "mni2ref_warp")

    return workflow
