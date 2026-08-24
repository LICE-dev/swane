from nipype import Node, IdentityInterface, SelectFiles, Merge
from nipype.interfaces.fsl import (
    MELODIC,
    FilterRegressor,
    ConvertWarp,
)
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow
from swane.nipype_pipeline.nodes.utils import (
    get_registration_node,
    apply_registration_node,
)
from swane.config.config_enums import SliceTiming, RegistrationEngine
from ica_aroma_py.services.ICA_AROMA_nodes import (
    FeatureTimeSeries,
    FeatureFrequency,
    AromaClassification,
    FeatureSpatial,
    FeatureSpatialPrep,
)
from ica_aroma_py import aroma_mask_out, aroma_mask_edge, aroma_mask_csf
import os


def fMRI_resting_state_workflow(
    name: str,
    dicom_dir: str,
    config: SectionProxy,
    base_dir: str = "/",
    test_run: bool = False,
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
    test_run : bool, optional
        If True, speed up the ref-to-atlas registration for prerelease test
        runs at the cost of accuracy. melodic_dim is never touched: the
        phantom dataset used for testing is built to yield a specific
        component count. The default is False.

    Input Node Fields
    ----------
    reference_brain : path
        Betted T13D.

    Output Node Fields
    ----------
    IC : path
        Independent components 4d nifti.
    mel_mix : path
        melodic_mix file from Melodic run

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
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=n_vols,
        hpcutoff=100,
        del_start_vols=del_start_vols,
        del_end_vols=del_end_vols,
        base_dir=base_dir,
        test_run=test_run,
    )

    # TODO: preference for melodic dim and threshold

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=["thresh_zstat_files", "aroma_classification", "mel_mix"]
        ),
        name="outputnode",
    )

    # Get nodes for further connection
    getTR = workflow.get_node("%s_getTR" % name)
    meanfuncmask = workflow.get_node("%s_meanfuncmask" % name)
    motion_correct = workflow.get_node("%s_motion_correct" % name)
    dilatemask = workflow.get_node("%s_dilatemask" % name)
    flirt_2_ref = workflow.get_node("%s_2_ref_flirt" % name)
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
        # When running aroma, the first melodic run dim must be automatic and not capped by user configuration, to ensure noise identification
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
            preproc_melodic_output,
            "thresh_zstat_files",
            feature_spatial_prep,
            "in_files",
        )
        workflow.connect(meanfuncmask, "mask_file", feature_spatial_prep, "mask_file")

        mni2 = os.path.join(
            os.environ["FSLDIR"], "data", "standard", "MNI152_T1_2mm_brain.nii.gz"
        )

        # Stick to FSL intentionally avoiding synth for reproducibility reason
        reg_2_mni = get_registration_node(
            name="ref_2_mni",
            name_prefix=name,
            name_suffix="to atlas",
            engine=RegistrationEngine.FSL,
            workflow=workflow,
            moving=[inputnode, "reference_brain"],
            reference=mni2,
            non_linear=True,
            inverse=False,
            flirt_cost="corratio",
            flirt_search=90,
            test_run=test_run,
        )

        # Combine func-to-ref linear matrix + ref-to-mni nonlinear warp into
        # single warp field, no premat on ApplyWarp.
        convert_warp = Node(ConvertWarp(), name="func_2_mni_warp")
        convert_warp.long_name = "func to atlas warp combination"
        convert_warp.inputs.reference = mni2
        workflow.connect(flirt_2_ref, "out_matrix_file", convert_warp, "premat")
        workflow.connect(
            reg_2_mni.out_registered_node, reg_2_mni.warp, convert_warp, "warp1"
        )

        # Stick to FSL intentionally avoiding synth for reproducibility reason
        apply_warp = apply_registration_node(
            name="func2mni",
            engine=RegistrationEngine.FSL,
            workflow=workflow,
            warp=[convert_warp, "out_file"],
            moving=[feature_spatial_prep, "out_file"],
            reference=mni2,
            non_linear=True,
        )

        feature_spatial = Node(FeatureSpatial(), name="feature_spatial")
        feature_spatial.inputs.mask_csf = aroma_mask_csf
        feature_spatial.inputs.mask_edge = aroma_mask_edge
        feature_spatial.inputs.mask_out = aroma_mask_out
        workflow.connect(apply_warp, "out_file", feature_spatial, "in_file")

        feature_time_series = Node(FeatureTimeSeries(), name="feature_time_series")
        workflow.connect(motion_correct, "par_file", feature_time_series, "mc")
        workflow.connect(
            preproc_melodic_output, "mel_mix", feature_time_series, "mel_mix"
        )

        feature_frequency = Node(FeatureFrequency(), name="feature_frequency")
        workflow.connect(getTR, "TR", feature_frequency, "TR")
        workflow.connect(
            preproc_melodic_output, "mel_ft_mix", feature_frequency, "mel_ft_mix"
        )

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
        workflow.connect(
            preproc_melodic_output, "mel_mix", nonaggr_denoising, "design_file"
        )
        workflow.connect(
            aroma_classification, "motion_ics", nonaggr_denoising, "filter_columns"
        )

        input_list_denoised = Node(Merge(1), name="input_list_denoised")
        input_list_denoised.long_name = "Denoised input for Melodic"
        workflow.connect(nonaggr_denoising, "out_file", input_list_denoised, "in1")

        workflow.connect(input_list_denoised, "out", melodic, "in_files")

    melodic.inputs.mm_thresh = melodic_thr
    # melodic_dim is never overridden by test_run: the phantom dataset is
    # built to yield a specific component count, which forcing a fixed dim
    # would defeat.
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

    zstats_2_ref = apply_registration_node(
        name="zstats",
        engine=RegistrationEngine.FSL,
        workflow=workflow,
        warp=[flirt_2_ref, "out_matrix_file"],
        moving=[melodic_output, "thresh_zstat_files"],
        reference=[inputnode, "reference_brain"],
        out_file=[melodic_output, ("thresh_zstat_files", registered_file_name)],
        non_linear=False,
        name_prefix="Zstat maps",
        name_suffix="to reference",
        iterfield=["in_file", "out_file"],
    )

    workflow.connect(zstats_2_ref, "out_file", outputnode, "thresh_zstat_files")
    workflow.connect(melodic_output, "mel_mix", outputnode, "mel_mix")

    return workflow


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
        # Search for a number before the .nii or .nii.gz extension
        m = re.search(r"(\d+)(\.nii(?:\.gz)?)$", base_name)
        if m:
            num = int(m.group(1))
            ext = m.group(2)
            new_name = re.sub(r"\d+(\.nii(?:\.gz)?)$", f"{num:02d}{ext}", base_name)
        else:
            new_name = base_name
        out_files.append("r-" + new_name)
    return out_files
