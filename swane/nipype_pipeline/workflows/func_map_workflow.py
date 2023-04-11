from nipype.interfaces.freesurfer import SampleToSurface
from nipype.interfaces.fsl import (FLIRT, IsotropicSmooth, ApplyWarp, ApplyMask, SwapDimensions, ApplyXFM)
from nipype.pipeline.engine import Node
from swane.nipype_pipeline.workflows.tractography_workflow import SIDES

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.AsymmetryIndex import AsymmetryIndex
from swane.nipype_pipeline.nodes.Zscore import Zscore

from nipype.interfaces.utility import IdentityInterface

import swane_supplement


def func_map_workflow(name: str, dicom_dir: str, is_freesurfer: bool, is_ai: bool, base_dir: str = "/") -> CustomWorkflow:
    """
    Analysis for PET or ASL:
        - registration to reference;
        - z-score and asymmetry index maps;
        - projection on FreeSurfer pial surface.

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The file path of the DICOM files.
    is_freesurfer : bool
        True if the reconall is available.
    is_ai : bool
        Enables the asymmetry index map calculation.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
        
    Input Node Fields
    ----------
    reference : path
        The reference image for the registration.
    brain_mask : path
        The brain mask from T13D bet command.
    freesurfer_subjects_dir : path
        The directory from FreeSurfer analysis.
    freesurfer_subject_id : 
        The subject id from FreeSurfer analysis.
    bgtROI : path
        Basal ganglia and thalami ROI.
    ref_2_sym_warp : path
        Nonlinear registration warp from T13D to symmetric atlas.
    ref_2_sym_invwarp : path
        Nonlinear registration inverse warp from symmetric atlas to T13D.

    Returns
    -------
    workflow : CustomWorkflow
        The func map workflow.
        
    Output Node Fields
    ----------
    registered_file : string
        Functional map in T13D reference space.
    surf_lh : path
        If FreeSurfer is available, functional map projection on LH pial surface.
    surf_rh : path
        If FreeSurfer is available, functional map projection on RH pial surface.
    zscore : path
        If FreeSurfer is available, internal z-score statistics compared to bgt.
    zscore_surf_lh : list of strings
        If FreeSurfer is available, z-score projection on LH pial surface.
    zscore_surf_rh : list of strings
        If FreeSurfer is available, z-score projection on RH pial surface.
    ai : path
        If AI is enabled, asymmetry index map.
    ai_surf_lh : path
        If FreeSurfer is available, asymmetry index projection on LH pial surface.
    ai_surf_rh : path
        If FreeSurfer is available, asymmetry index projection on RH pial surface.

    """
    
    workflow = CustomWorkflow(name=name, base_dir=base_dir)
    
    # Input Node
    inputnode = Node(
        IdentityInterface(fields=['reference', 'brain_mask', 'freesurfer_subjects_dir',
                                  'freesurfer_subject_id', 'bgtROI', 'ref_2_sym_warp',
                                  'swap_2_sym_warp', 'ref_2_sym_invwarp']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['registered_file', 'surf_lh', 'surf_rh', 'zscore', 'zscore_surf_lh',
                                  'zscore_surf_rh', 'ai', 'ai_surf_lh', 'ai_surf_rh']),
        name='outputnode')

    # NODE 1: Conversion dicom -> nifti
    conv = Node(CustomDcm2niix(), name='%s_conv' % name)
    conv.inputs.out_filename = name
    conv.inputs.bids_format = False
    conv.inputs.source_dir = dicom_dir

    # NODE 2: Orienting in radiological convention
    reorient = Node(ForceOrient(), name='%s_reOrient' % name)
    workflow.connect(conv, "converted_files", reorient, "in_file")

    # NODE 3: Gaussian smoothing
    smooth = Node(IsotropicSmooth(), name='%s_smooth' % name)
    smooth.long_name = "smoothing"
    smooth.inputs.sigma = 2
    workflow.connect(reorient, "out_file", smooth, "in_file")

    # NODE 4: Registration matrix calculation in reference space
    func_2_ref_flirt = Node(FLIRT(), name='%s_2_ref_flirt' % name)
    func_2_ref_flirt.long_name = "%s to reference space"
    func_2_ref_flirt.inputs.cost = "mutualinfo"
    func_2_ref_flirt.inputs.searchr_x = [-90, 90]
    func_2_ref_flirt.inputs.searchr_y = [-90, 90]
    func_2_ref_flirt.inputs.searchr_z = [-90, 90]
    func_2_ref_flirt.inputs.dof = 6
    func_2_ref_flirt.inputs.interp = "trilinear"
    workflow.connect(reorient, "out_file", func_2_ref_flirt, "in_file")
    workflow.connect(inputnode, "reference", func_2_ref_flirt, "reference")

    # NODE 5: Smooth volume linear transformation in reference space
    smooth_2_ref_flirt = Node(ApplyXFM(), name='%s_smooth_2_ref_flirt' % name)
    smooth_2_ref_flirt.long_name = "%s to reference space"
    smooth_2_ref_flirt.inputs.out_file = "r-%s.nii.gz" % name
    smooth_2_ref_flirt.inputs.interp = "trilinear"
    workflow.connect(smooth, "out_file", smooth_2_ref_flirt, "in_file")
    workflow.connect(inputnode, "reference", smooth_2_ref_flirt, "reference")
    workflow.connect(func_2_ref_flirt, "out_matrix_file", smooth_2_ref_flirt, "in_matrix_file")

    # NODE 6: Scalp removal
    mask = Node(ApplyMask(), name='%s_mask' % name)
    mask.long_name = name + " %s"
    mask.inputs.out_file = 'r-%s.nii.gz' % name
    workflow.connect(smooth_2_ref_flirt, "out_file", mask, "in_file")
    workflow.connect(inputnode, "brain_mask", mask, "mask_file")

    workflow.connect(mask, "out_file", outputnode, "registered_file")

    if is_freesurfer:
        # NODE 7: Projection of the map on FreeSurfer pial surface
        for side in SIDES:
            func_surf = Node(SampleToSurface(), name='%s_surf_%s' % (name, side))
            func_surf.long_name = side + " " + name + " %s"
            func_surf.inputs.hemi = side
            func_surf.inputs.out_file = "%s_surf_%s.mgz" % (name, side)
            func_surf.inputs.cortex_mask = True
            func_surf.inputs.reg_header = True
            func_surf.inputs.sampling_method = "point"
            func_surf.inputs.sampling_range = 0.5
            func_surf.inputs.sampling_units = "frac"
            workflow.connect(mask, "out_file", func_surf, "source_file")
            workflow.connect(inputnode, "freesurfer_subjects_dir", func_surf, "subjects_dir")
            workflow.connect(inputnode, "freesurfer_subject_id", func_surf, "subject_id")

            workflow.connect(func_surf, "out_file", outputnode, "surf_%s" % side)

        # NODE 8: z-score calculation
        zscore = Node(Zscore(), name="%s_zscore" % name)
        zscore.long_name = "internal zscore"
        zscore.inputs.out_file = "r-%s_zscore.nii.gz" % name
        workflow.connect(mask, "out_file", zscore, "in_file")
        workflow.connect(inputnode, "bgtROI", zscore, "ROI_file")

        workflow.connect(zscore, "out_file", outputnode, "zscore")

        # NODE 10: Projection of z-score on FreeSurfer pial surface
        for side in SIDES:
            zscore_surf_lh = Node(SampleToSurface(), name='%s_zscore_surf_%s' % (name, side))
            zscore_surf_lh.long_name = side + " zscore %s"
            zscore_surf_lh.inputs.hemi = side
            zscore_surf_lh.inputs.out_file = "%s_zscore_surf_%s.mgz" % (name, side)
            zscore_surf_lh.inputs.cortex_mask = True
            zscore_surf_lh.inputs.reg_header = True
            zscore_surf_lh.inputs.sampling_method = "point"
            zscore_surf_lh.inputs.sampling_range = 0.5
            zscore_surf_lh.inputs.sampling_units = "frac"
            workflow.connect(zscore, "out_file", zscore_surf_lh, "source_file")
            workflow.connect(inputnode, "freesurfer_subjects_dir", zscore_surf_lh, "subjects_dir")
            workflow.connect(inputnode, "freesurfer_subject_id", zscore_surf_lh, "subject_id")

            workflow.connect(zscore_surf_lh, "out_file", outputnode, "zscore_surf_%s" % side)

    if is_ai:
        sym_template = swane_supplement.sym_template

        # NODE 11: Nonlinear transformation of the images in symmetric atlas
        func_2_sym_warp = Node(ApplyWarp(), name='%s_2_sym_warp' % name)
        func_2_sym_warp.long_name = "%s to symmetric atlas"
        func_2_sym_warp.inputs.ref_file = sym_template
        workflow.connect(mask, "out_file", func_2_sym_warp, "in_file")
        workflow.connect(inputnode, "ref_2_sym_warp", func_2_sym_warp, "field_file")

        # NODE 12: RL swap of image in symmetric atlas
        sym_swap = Node(SwapDimensions(), name='%s_sym_swap' % name)
        sym_swap.long_name = "right-left flip"
        sym_swap.inputs.out_file = "%s_sym_swapped.nii.gz" % name
        sym_swap.inputs.new_dims = ("-x", "y", "z")
        workflow.connect(func_2_sym_warp, "out_file", sym_swap, "in_file")

        # NODE 13: Asymmetry index calculation
        ai = Node(AsymmetryIndex(), name="%s_ai" % name)
        ai.long_name = "asymmetry index"
        ai.inputs.out_file = "r-%s_ai.nii.gz" % name
        workflow.connect(func_2_sym_warp, "out_file", ai, "in_file")
        workflow.connect(sym_swap, "out_file", ai, "swapped_file")

        # NODE 14: AI Nonlinear transformation to reference space
        ai_2_ref = Node(ApplyWarp(), name="%s_ai_2_ref" % name)
        ai_2_ref.long_name = "asymmetry index %s from symmetric atlas"
        ai_2_ref.inputs.out_file = "r-%s_ai.nii.gz" % name
        workflow.connect(ai, "out_file", ai_2_ref, "in_file")
        workflow.connect(inputnode, "ref_2_sym_invwarp", ai_2_ref, "field_file")
        workflow.connect(inputnode, "reference", ai_2_ref, "ref_file")

        workflow.connect(ai_2_ref, "out_file", outputnode, "ai")

        if is_freesurfer:
            for side in SIDES:
                # NODE 15: Projection of AI on FreeSurfer pial surface
                ai_surf = Node(SampleToSurface(), name='%s_ai_surf_%s' % (name, side))
                ai_surf.long_name = side + " asymmetry index %s"
                ai_surf.inputs.hemi = side
                ai_surf.inputs.out_file = "%s_ai_surf_%s.mgz" % (name, side)
                ai_surf.inputs.cortex_mask = True
                ai_surf.inputs.reg_header = True
                ai_surf.inputs.sampling_method = "point"
                ai_surf.inputs.sampling_range = 0.5
                ai_surf.inputs.sampling_units = "frac"
                workflow.connect(ai_2_ref, "out_file", ai_surf, "source_file")
                workflow.connect(inputnode, "freesurfer_subjects_dir", ai_surf, "subjects_dir")
                workflow.connect(inputnode, "freesurfer_subject_id", ai_surf, "subject_id")

                workflow.connect(ai_surf, "out_file", outputnode, "ai_surf_%s" % side)

    return workflow
