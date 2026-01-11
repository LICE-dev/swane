from nipype import Node, IdentityInterface, SelectFiles, MapNode, Merge
from nipype.interfaces.fsl import (
    MELODIC,
    ApplyXFM,
    FLIRT,
    FNIRT,
    ApplyWarp,
    FilterRegressor,
)
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow
from swane.config.config_enums import SLICE_TIMING
from ica_aroma_py.services.ICA_AROMA_nodes import (
    FeatureTimeSeries,
    FeatureFrequency,
    AromaClassification,
    FeatureSpatial,
    FeatureSpatialPrep,
    IsoResample,
)
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
    run_aroma = config.getboolean_safe("aroma")
    melodic_dim = config.getint_safe("melodic_dim")
    melodic_thr = config.getfloat_safe("melodic_thr")

    workflow = fMRI_preproc_workflow(
        name=name,
        dicom_dir=dicom_dir,
        TR=TR,
        slice_timing=SLICE_TIMING.UNKNOWN,
        n_vols=n_vols,
        hpcutoff=100,
        del_start_vols=del_start_vols,
        del_end_vols=del_end_vols,
        base_dir=base_dir,
    )

    #TODO: preference per melodic dim e per soglia

    # Output Node
    outputnode = Node(
        IdentityInterface(fields=["thresh_zstat_files", "aroma_classification"]),
        name="outputnode",
    )

    # Get nodes for further connection
    getTR = workflow.get_node("%s_getTR" % name)
    meanfuncmask = workflow.get_node("%s_meanfuncmask" % name)
    motion_correct = workflow.get_node("%s_motion_correct" % name)
    dilatemask = workflow.get_node("%s_dilatemask" % name)
    flirt_2_ref = workflow.get_node("%s_flirt_2_ref" % name)
    highpass = workflow.get_node(
        "%s_highpass" % name
    )  # this is the final preprocessing file
    inputnode = workflow.get_node("inputnode")

    input_list = Node(Merge(1), name="merge_node")
    input_list.long_name = "Select input for Melodic"
    workflow.connect(highpass, "out_file", input_list, "in1")

    templates = dict(
        IC="melodic_IC.nii.gz",
        mel_mix="melodic_mix",
        mel_ft_mix="melodic_FTmix",
        thresh_zstat_files="stats/thresh_zstat*.nii.gz",
    )

    # Declare here for conditional connect based on run_aroma preference
    melodic = Node(MELODIC(), name="melodic")

    if not run_aroma:
        workflow.connect(input_list, "out", melodic, "in_files")
    else:
        preproc_melodic = Node(MELODIC(), name="preproc_melodic")
        preproc_melodic.inputs.mm_thresh = 0.5
        # TODO: valutare se creare una impostazione per limitare il numero di IC
        preproc_melodic.inputs.dim = 0
        preproc_melodic.inputs.out_stats = True
        preproc_melodic.inputs.no_bet = True
        preproc_melodic.inputs.report = True
        workflow.connect(input_list, "out", preproc_melodic, "in_files")
        workflow.connect(meanfuncmask, "mask_file", preproc_melodic, "mask")
        workflow.connect(getTR, "TR", preproc_melodic, "tr_sec")

        preproc_melodic_output = Node(
            SelectFiles(templates), name="preproc_melodic_output"
        )
        preproc_melodic_output.inputs.sorted = True
        workflow.connect(
            preproc_melodic, "out_dir", preproc_melodic_output, "melodic_dir"
        )
        workflow.connect(
            preproc_melodic, "out_dir", preproc_melodic_output, "base_directory"
        )


        feature_spatial_prep = Node(FeatureSpatialPrep(), name="feature_spatial_prep")
        workflow.connect(
            preproc_melodic_output, "thresh_zstat_files", feature_spatial_prep, "in_files"
        )
        workflow.connect(meanfuncmask, "mask_file", feature_spatial_prep, "mask_file")

        mni2 = os.path.join(
            os.environ["FSLDIR"], "data", "standard", "MNI152_T1_2mm_brain.nii.gz"
        )

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

        feature_spatial = Node(FeatureSpatial(), name="feature_spatial")
        feature_spatial.inputs.mask_csf = aroma_mask_csf
        feature_spatial.inputs.mask_edge = aroma_mask_edge
        feature_spatial.inputs.mask_out = aroma_mask_out
        workflow.connect(apply_warp, "out_file", feature_spatial, "in_file")

        feature_time_series = Node(FeatureTimeSeries(), name="feature_time_series")
        workflow.connect(motion_correct, "par_file", feature_time_series, "mc")
        workflow.connect(preproc_melodic_output, "mel_mix", feature_time_series, "mel_mix")

        feature_frequency = Node(FeatureFrequency(), name="feature_frequency")
        workflow.connect(getTR, "TR", feature_frequency, "TR")
        workflow.connect(preproc_melodic_output, "mel_ft_mix", feature_frequency, "mel_ft_mix")

        aroma_classification = Node(AromaClassification(), name="aroma_classification")
        workflow.connect(feature_frequency, "HFC", aroma_classification, "HFC")
        workflow.connect(
            feature_time_series, "max_rp_corr", aroma_classification, "max_rp_corr"
        )
        workflow.connect(
            feature_spatial, "csf_fract", aroma_classification, "csf_fract"
        )
        workflow.connect(
            feature_spatial, "edge_fract", aroma_classification, "edge_fract"
        )

        workflow.connect(
            aroma_classification,
            "classification_overview",
            outputnode,
            "aroma_classification",
        )

        nonaggr_denoising = Node(FilterRegressor(), name="nonaggr_denoising", mem_gb=5)
        nonaggr_denoising.inputs.out_file = "denoised_func_data_nonaggr.nii.gz"
        workflow.connect(highpass, "out_file", nonaggr_denoising, "in_file")
        workflow.connect(preproc_melodic_output, "mel_mix", nonaggr_denoising, "design_file")
        workflow.connect(
            aroma_classification, "motion_ics", nonaggr_denoising, "filter_columns"
        )

        input_list_denoised = Node(Merge(1), name="input_list_denoised")
        input_list_denoised.long_name = "Denoised input for Melodic"
        workflow.connect(nonaggr_denoising, "out_file", input_list_denoised, "in1")

        workflow.connect(input_list_denoised, "out", melodic, "in_files")

    melodic.inputs.mm_thresh = melodic_thr
    melodic.inputs.dim = melodic_dim
    melodic.inputs.out_stats = True
    melodic.inputs.no_bet = True
    melodic.inputs.report = True
    workflow.connect(dilatemask, "out_file", melodic, "mask")
    workflow.connect(getTR, "TR", melodic, "tr_sec")

    melodic_output = Node(SelectFiles(templates), name="melodic_output")
    melodic_output.inputs.sorted = True
    workflow.connect(melodic, "out_dir", melodic_output, "melodic_dir")
    workflow.connect(melodic, "out_dir", melodic_output, "base_directory")

    # Function to generate the name for the file of registered output zstats
    def registered_file_name(in_file_names):
        """
        Adds prefix 'r-' and use 2 digid number at end.
        Example: 'zstat1.nii.gz' -> 'r-zstat01.nii.gz'
        """
        from os.path import basename
        import re

        out_files = []
        for f in in_file_names:
            base_name = basename(f)
            # Cerca un numero prima dell'estensione .nii o .nii.gz
            m = re.search(r"(\d+)(\.nii(?:\.gz)?)$", base_name)
            if m:
                num = int(m.group(1))
                ext = m.group(2)
                new_name = re.sub(r"\d+(\.nii(?:\.gz)?)$", f"{num:02d}{ext}", base_name)
            else:
                new_name = base_name
            out_files.append("r-" + new_name)
        return out_files

    zstats_2_ref = MapNode(
        ApplyXFM(), name="zstats_2_ref", iterfield=["in_file", "out_file"]
    )
    workflow.connect(flirt_2_ref, "out_matrix_file", zstats_2_ref, "in_matrix_file")
    workflow.connect(inputnode, "ref_brain", zstats_2_ref, "reference")
    workflow.connect(melodic_output, "thresh_zstat_files", zstats_2_ref, "in_file")
    workflow.connect(
        melodic_output,
        ("thresh_zstat_files", registered_file_name),
        zstats_2_ref,
        "out_file",
    )

    workflow.connect(zstats_2_ref, "out_file", outputnode, "thresh_zstat_files")

    return workflow
