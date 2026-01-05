from nipype import Node, IdentityInterface, SelectFiles, Merge
from nipype.interfaces.fsl import (
    MELODIC,
    ApplyXFM,
    ImageMaths,
    FLIRT,
    FNIRT,
    ApplyWarp,
    InvWarp,
    ConvertXFM

)
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow
from swane.config.config_enums import SLICE_TIMING
from ica_aroma_py.services.ICA_AROMA_nodes import (FeatureTimeSeries, FeatureFrequency,
                              AromaClassification, FeatureSpatial, FeatureSpatialPrep, IsoResample)
from ica_aroma_py import aroma_mask_out, aroma_mask_edge, aroma_mask_csf
import os

def fMRI_resting_state_workflow(
    name: str, dicom_dir: str, config: SectionProxy, base_dir: str = "/"
) -> CustomWorkflow:
    """
    fMRI resting state anlysis

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The directory path of the DICOM files.
    config: SectionProxy
        workflow settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    ref_brain : path
        Betted T13D.

    Output Node Fields
    ----------
    IC : path
        Independent components 4d nifti.

    Returns
    -------
    workflow : CustomWorkflow
        The fMRI workflow.

    """

    TR = config.getfloat_safe("tr")
    n_vols = config.getint_safe("n_vols")
    del_start_vols = config.getint_safe("del_start_vols")
    del_end_vols = config.getint_safe("del_end_vols")

    workflow = fMRI_preproc_workflow(name=name, dicom_dir=dicom_dir, TR=TR, slice_timing=SLICE_TIMING.UNKNOWN, n_vols=n_vols,
                                     hpcutoff=100, del_start_vols=del_start_vols, del_end_vols=del_end_vols,
                                     base_dir=base_dir)

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "IC",
            ]
        ),
        name="outputnode",
    )

    # Get nodes for further connection
    getTR = workflow.get_node("%s_getTR" % name)
    del_vols = workflow.get_node("%s_del_vols" % name)
    motion_correct = workflow.get_node("%s_motion_correct" % name)
    dilatemask = workflow.get_node("%s_dilatemask" % name)
    flirt_2_ref = workflow.get_node("%s_flirt_2_ref" % name)
    highpass = workflow.get_node("%s_highpass" % name) # this is the final preprocessing file
    inputnode = workflow.get_node("inputnode")

    input_list = Node(Merge(1), name="merge_node")
    workflow.connect(highpass, "out_file", input_list, "in1")

    melodic = Node(MELODIC(), name="melodic")
    melodic.inputs.mm_thresh = 0.5
    # TODO: valutare se creare una impostazione per limitare il numero di IC
    melodic.inputs.dim = 0
    melodic.inputs.out_stats = True
    melodic.inputs.no_bet = True
    melodic.inputs.report = True
    workflow.connect(input_list, "out", melodic, "in_files")
    workflow.connect(dilatemask, "out_file", melodic, "mask")
    workflow.connect(getTR, "TR", melodic, "tr_sec")

    templates = dict(IC="melodic_IC.nii.gz",
                     mel_mix="melodic_mix",
                     mel_ft_mix="melodic_FTmix",
                     thresh_zstat_files="stats/thresh_zstat*.nii.gz")

    melodic_output = Node(SelectFiles(templates), name="melodic_output")
    melodic_output.inputs.sorted = True
    workflow.connect(melodic, "out_dir", melodic_output, "melodic_dir")
    workflow.connect(melodic, "out_dir", melodic_output, "base_directory")

    mask_maths = Node(ImageMaths(), name="create_mask_maths")
    mask_maths.inputs.op_string = '-Tstd -bin'
    mask_maths.inputs.out_file = "brain_mask.nii.gz"
    workflow.connect(highpass, "out_file", mask_maths, "in_file")

    feature_spatial_prep = Node(FeatureSpatialPrep(), name="feature_spatial_prep")
    workflow.connect(melodic_output, "thresh_zstat_files", feature_spatial_prep, "in_files")
    workflow.connect(mask_maths, "out_file", feature_spatial_prep, "mask_file")


    ###########################################

    mni2 = os.path.join(os.environ["FSLDIR"], 'data', 'standard', 'MNI152_T1_2mm_brain.nii.gz')

    flirt = Node(FLIRT(), name="ref_2_mni_flirt")
    flirt.long_name = "%s to atlas"
    flirt.inputs.searchr_x = [-90, 90]
    flirt.inputs.searchr_y = [-90, 90]
    flirt.inputs.searchr_z = [-90, 90]
    flirt.inputs.dof = 12
    flirt.inputs.cost = "corratio"
    flirt.inputs.out_matrix_file = "ref_2_mni.mat"
    flirt.inputs.reference = mni2
    workflow.connect(inputnode, "ref_brain", flirt, "in_file")

    # NODE 2: Nonlinear registration
    fnirt = Node(FNIRT(), name="ref_2_mni_fnirt")
    fnirt.long_name = "%s to atlas"
    fnirt.inputs.fieldcoeff_file = True
    fnirt.inputs.ref_file = mni2
    workflow.connect(flirt, "out_matrix_file", fnirt, "affine_file")
    workflow.connect(inputnode, "ref_brain", fnirt, "in_file")

    apply_warp = Node(ApplyWarp(), name="func2mni")
    apply_warp.inputs.ref_file = mni2
    workflow.connect(flirt_2_ref, "out_matrix_file", apply_warp, "premat")
    workflow.connect(feature_spatial_prep, "out_file", apply_warp, "in_file")
    workflow.connect(fnirt, "fieldcoeff_file", apply_warp, "field_file")

    ##########################################################

    feature_spatial = Node(FeatureSpatial(), name="feature_spatial")
    feature_spatial.inputs.mask_csf = aroma_mask_csf
    feature_spatial.inputs.mask_edge = aroma_mask_edge
    feature_spatial.inputs.mask_out = aroma_mask_out
    workflow.connect(apply_warp, "out_file", feature_spatial, "in_file")

    feature_time_series = Node(FeatureTimeSeries(), name="feature_time_series")
    workflow.connect(motion_correct, "par_file", feature_time_series, "mc")
    workflow.connect(melodic_output, "mel_mix", feature_time_series, "mel_mix")

    feature_frequency = Node(FeatureFrequency(), name="feature_frequency")
    workflow.connect(getTR, "TR", feature_frequency, "TR")
    workflow.connect(melodic_output, "mel_ft_mix", feature_frequency, "mel_ft_mix")

    aroma_classification = Node(AromaClassification(), name="aroma_classification")
    workflow.connect(feature_frequency, "HFC", aroma_classification, "HFC")
    workflow.connect(feature_time_series, "max_rp_corr", aroma_classification, "max_rp_corr")
    workflow.connect(feature_spatial, "csf_fract", aroma_classification, "csf_fract")
    workflow.connect(feature_spatial, "edge_fract", aroma_classification, "edge_fract")

    #workflow.connect(aroma_classification, "feature_scores", outputnode, "ica_aroma_results.@feature_scores")
    #workflow.connect(aroma_classification, "classified_motion_ics", aroma_datasink, "ica_aroma_results.@classified_motion_ics")
    workflow.connect(aroma_classification, "classification_overview", outputnode, "IC")

    return workflow
