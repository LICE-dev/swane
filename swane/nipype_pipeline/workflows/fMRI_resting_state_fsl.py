from nipype import Node, SelectFiles, Merge
from nipype.interfaces.fsl import MELODIC, FilterRegressor
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.interfaces.niimath import ImageMaths
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import (
    highpass_op_string_function,
)
from swane.nipype_pipeline.workflows.fMRI_resting_state_aroma import (
    build_aroma_classification,
)
from swane.config.config_enums import RegistrationEngine


def build_fsl_resting(
    workflow: CustomWorkflow,
    name: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    engine: RegistrationEngine,
    test_run: bool = False,
    max_cpu: int = 0,
    hpcutoff: float = 100,
) -> Node:
    """
    Add the FSL MELODIC resting-state analysis to a preprocessed workflow.

    Without ICA-AROMA, MELODIC runs on the high-pass filtered data in the
    dilated mask. With ICA-AROMA, following the order of Pruim et al. 2015a
    NeuroImage 112:267 (AROMA before temporal filtering):

    1. ``preproc_melodic`` decomposes the unfiltered intensity-normalised data
       (``%s_intnorm``) in the bold brain mask;
    2. the shared AROMA module classifies its components;
    3. ``nonaggr_denoising`` (``fsl_regfilt``, non-aggressive) removes the
       motion components from the unfiltered data;
    4. ``%s_highpass_denoised`` applies the ``-bptf`` high-pass of the
       preprocessing (same op string, same cutoff) plus the temporal mean
       (``%s_meanfunc_denoised``);
    5. the final ``melodic`` decomposes the filtered, denoised data.

    Parameters
    ----------
    workflow : CustomWorkflow
        The workflow built by ``fMRI_preproc_workflow``.
    name : str
        The workflow name (the prefix of the preprocessing node names).
    config : SectionProxy
        The resting-state workflow settings (``aroma``, ``ic_dim``,
        ``melodic_thr``).
    synth_config : SectionProxy
        The Synth-tools configuration section.
    engine : RegistrationEngine
        The resolved EPI registration engine.
    test_run : bool, optional
        If True, speed up the ref-to-atlas registration. The default is False.
    max_cpu : int, optional
        Per-subject CPU budget for the registration. The default is 0.
    hpcutoff : float, optional
        The high-pass cutoff in seconds, the same passed to the
        preprocessing. The default is 100.

    Returns
    -------
    Node
        The final MELODIC output node, with fields ``thresh_zstat_files`` and
        ``ic_mix``.

    """
    run_aroma = config.getboolean_safe("aroma")
    melodic_dim = config.getint_safe("ic_dim")
    melodic_thr = config.getfloat_safe("melodic_thr")

    getTR = workflow.get_node("%s_getTR" % name)
    meanfuncmask = workflow.meanfuncmask
    motion_correct = workflow.get_node("%s_motion_correct" % name)
    dilatemask = workflow.get_node("%s_dilatemask" % name)
    highpass = workflow.get_node("%s_highpass" % name)
    intnorm = workflow.intnorm_node
    inputnode = workflow.get_node("inputnode")

    input_list = Node(Merge(1), name="merge_node")
    input_list.long_name = "Select input for Melodic"
    if run_aroma:
        # The AROMA pass decomposes the unfiltered data.
        workflow.connect(intnorm, "out_file", input_list, "in1")
    else:
        workflow.connect(highpass, "out_file", input_list, "in1")

    templates = dict(
        IC="melodic_IC.nii.gz",
        mel_mix="melodic_mix",
        mel_ft_mix="melodic_FTmix",
        thresh_zstat_files="stats/thresh_zstat*.nii.gz",
    )
    # The final output exposes the mixing matrix as ``ic_mix``.
    final_templates = dict(
        IC="melodic_IC.nii.gz",
        ic_mix="melodic_mix",
        mel_ft_mix="melodic_FTmix",
        thresh_zstat_files="stats/thresh_zstat*.nii.gz",
    )

    if not run_aroma:
        melodic = Node(MELODIC(), name="melodic")
        melodic.inputs.mm_thresh = melodic_thr
        melodic.inputs.dim = melodic_dim
        melodic.inputs.out_stats = True
        melodic.inputs.no_bet = True
        melodic.inputs.report = True
        workflow.connect(input_list, "out", melodic, "in_files")
        workflow.connect(dilatemask, "out_file", melodic, "mask")
        workflow.connect(getTR, "TR", melodic, "tr_sec")

        ica_output = Node(SelectFiles(final_templates), name="melodic_output")
        ica_output.inputs.sorted = True
        workflow.connect(melodic, "out_dir", ica_output, "melodic_dir")
        workflow.connect(melodic, "out_dir", ica_output, "base_directory")
        return ica_output

    preproc_melodic = Node(MELODIC(), name="preproc_melodic")
    preproc_melodic.inputs.mm_thresh = 0.5
    preproc_melodic.inputs.dim = 0
    preproc_melodic.inputs.out_stats = True
    preproc_melodic.inputs.no_bet = True
    preproc_melodic.inputs.report = True
    workflow.connect(input_list, "out", preproc_melodic, "in_files")
    workflow.connect(meanfuncmask, "mask_file", preproc_melodic, "mask")
    workflow.connect(getTR, "TR", preproc_melodic, "tr_sec")

    preproc_ica_output = Node(SelectFiles(templates), name="preproc_melodic_output")
    preproc_ica_output.inputs.sorted = True
    workflow.connect(preproc_melodic, "out_dir", preproc_ica_output, "melodic_dir")
    workflow.connect(preproc_melodic, "out_dir", preproc_ica_output, "base_directory")

    aroma_classification, _ = build_aroma_classification(
        workflow=workflow,
        ica_output=preproc_ica_output,
        mask_node=meanfuncmask,
        mask_field="mask_file",
        motion_correct=motion_correct,
        getTR=getTR,
        inputnode=inputnode,
        engine=engine,
        synth_config=synth_config,
        test_run=test_run,
        max_cpu=max_cpu,
    )

    nonaggr_denoising = Node(FilterRegressor(), name="nonaggr_denoising", mem_gb=5)
    nonaggr_denoising.inputs.out_file = "denoised_func_data_nonaggr.nii.gz"
    workflow.connect(intnorm, "out_file", nonaggr_denoising, "in_file")
    workflow.connect(preproc_ica_output, "mel_mix", nonaggr_denoising, "design_file")
    workflow.connect(
        aroma_classification, "motion_ics", nonaggr_denoising, "filter_columns"
    )

    # Temporal high-pass of the denoised data, as in the preprocessing: -bptf
    # removes the temporal mean, which is added back.
    meanfunc_denoised = Node(ImageMaths(), name="%s_meanfunc_denoised" % name)
    meanfunc_denoised.long_name = "mean image calculation"
    meanfunc_denoised.inputs.op_string = "-Tmean"
    meanfunc_denoised.inputs.suffix = "_mean"
    workflow.connect(nonaggr_denoising, "out_file", meanfunc_denoised, "in_file")

    merge_tr_meanfunc_denoised = Node(
        Merge(2), name="%s_merge_tr_meanfunc_denoised" % name
    )
    merge_tr_meanfunc_denoised.long_name = "Highpass filtering setup"
    workflow.connect(getTR, "TR", merge_tr_meanfunc_denoised, "in1")
    workflow.connect(meanfunc_denoised, "out_file", merge_tr_meanfunc_denoised, "in2")

    highpass_denoised = Node(ImageMaths(), name="%s_highpass_denoised" % name)
    highpass_denoised.long_name = "Highpass temporal filtering"
    highpass_denoised.inputs.suffix = "_tempfilt"
    workflow.connect(
        [
            (
                merge_tr_meanfunc_denoised,
                highpass_denoised,
                [(("out", highpass_op_string_function(), hpcutoff), "op_string")],
            )
        ]
    )
    workflow.connect(nonaggr_denoising, "out_file", highpass_denoised, "in_file")

    input_list_denoised = Node(Merge(1), name="input_list_denoised")
    input_list_denoised.long_name = "Denoised input for Melodic"
    workflow.connect(highpass_denoised, "out_file", input_list_denoised, "in1")

    melodic = Node(MELODIC(), name="melodic")
    melodic.inputs.mm_thresh = melodic_thr
    melodic.inputs.dim = melodic_dim
    melodic.inputs.out_stats = True
    melodic.inputs.no_bet = True
    melodic.inputs.report = True
    workflow.connect(input_list_denoised, "out", melodic, "in_files")
    workflow.connect(dilatemask, "out_file", melodic, "mask")
    workflow.connect(getTR, "TR", melodic, "tr_sec")

    ica_output = Node(SelectFiles(final_templates), name="melodic_output")
    ica_output.inputs.sorted = True
    workflow.connect(melodic, "out_dir", ica_output, "melodic_dir")
    workflow.connect(melodic, "out_dir", ica_output, "base_directory")

    return ica_output
