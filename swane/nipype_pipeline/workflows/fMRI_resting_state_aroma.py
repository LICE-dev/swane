from nipype import Node
from nipype.interfaces.fsl import ConvertWarp
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.interfaces.utils import (
    RegistrationNodeWrapper,
    get_registration_node,
    apply_registration_node,
)
from swane.config.config_enums import RegistrationEngine
from ica_aroma_py.services.ICA_AROMA_nodes import (
    FeatureTimeSeries,
    FeatureFrequency,
    AromaClassification,
    FeatureSpatial,
    FeatureSpatialPrep,
)
from ica_aroma_py import aroma_mask_out, aroma_mask_edge, aroma_mask_csf


def build_ref_2_mni(
    workflow: CustomWorkflow,
    inputnode: Node,
    engine: RegistrationEngine,
    synth_config: SectionProxy,
    test_run: bool = False,
    max_cpu: int = 0,
) -> tuple[RegistrationNodeWrapper, str]:
    """
    Add the nonlinear registration of the reference brain to MNI152NLin6Asym
    2 mm (node ``ref_2_mni``) to a resting-state workflow.

    Parameters
    ----------
    workflow : CustomWorkflow
        The resting-state workflow.
    inputnode : Node
        The workflow input node (``reference_brain``).
    engine : RegistrationEngine
        The resolved EPI registration engine.
    synth_config : SectionProxy
        The Synth-tools configuration section (``limit_cores``).
    test_run : bool, optional
        If True, speed up the registration. The default is False.
    max_cpu : int, optional
        Per-subject CPU budget for the registration. The default is 0.

    Returns
    -------
    tuple
        ``(reg_2_mni, mni2)``: the registration wrapper and the path of the
        MNI152NLin6Asym 2 mm brain template used as its reference.

    """
    from swane.utils.templates import get_swane_template

    mni2 = get_swane_template(
        name="MNI152NLin6Asym", resolution=2, desc="brain", enforce_las=True
    )

    reg_2_mni = get_registration_node(
        name="ref_2_mni",
        name_prefix=workflow.name,
        name_suffix="to atlas",
        engine=engine,
        workflow=workflow,
        moving=[inputnode, "reference_brain"],
        reference=mni2,
        non_linear=True,
        inverse=False,
        flirt_cost="corratio",
        flirt_search=90,
        test_run=test_run,
        max_cpu=max_cpu,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    return reg_2_mni, mni2


def build_aroma_classification(
    workflow: CustomWorkflow,
    ica_output: Node,
    mask_node: Node,
    mask_field: str,
    motion_correct: Node,
    getTR: Node,
    inputnode: Node,
    engine: RegistrationEngine,
    synth_config: SectionProxy,
    test_run: bool = False,
    max_cpu: int = 0,
) -> tuple[Node, RegistrationNodeWrapper]:
    """
    Add the ICA-AROMA feature extraction and classification to a resting-state
    workflow (Pruim et al. 2015a NeuroImage 112:267).

    The thresholded component maps are moved to MNI152NLin6Asym 2 mm for the
    spatial features; the time-series and frequency features use the component
    mixing matrix and its Fourier transform. The node names are shared by every
    fMRI engine: ``feature_spatial_prep``, ``ref_2_mni``, ``func2mni`` (plus
    ``func_2_mni_warp`` when the registration engine is not ANTs),
    ``feature_spatial``, ``feature_time_series``, ``feature_frequency`` and
    ``aroma_classification``.

    Parameters
    ----------
    workflow : CustomWorkflow
        The resting-state workflow, built on ``fMRI_preproc_workflow`` (it
        must expose ``workflow.reg_2_ref``).
    ica_output : Node
        The node carrying the AROMA-pass ICA outputs, with fields
        ``thresh_zstat_files`` (mixture-model thresholded maps), ``mel_mix``
        (mixing matrix) and ``mel_ft_mix`` (its Fourier spectra).
    mask_node : Node
        The node providing the functional brain mask.
    mask_field : str
        The output field of ``mask_node`` with the mask.
    motion_correct : Node
        The motion-correction node (its ``par_file`` feeds the time-series
        feature).
    getTR : Node
        The node providing the repetition time (``TR``).
    inputnode : Node
        The workflow input node (``reference_brain``).
    engine : RegistrationEngine
        The resolved EPI registration engine.
    synth_config : SectionProxy
        The Synth-tools configuration section (``limit_cores``).
    test_run : bool, optional
        If True, speed up the ref-to-atlas registration. The default is False.
    max_cpu : int, optional
        Per-subject CPU budget for the registration. The default is 0.

    Returns
    -------
    tuple
        ``(aroma_classification, reg_2_mni)``: the classification node (fields
        ``motion_ics`` and ``classification_overview``) and the ref-to-MNI
        registration wrapper.

    """
    feature_spatial_prep = Node(FeatureSpatialPrep(), name="feature_spatial_prep")
    workflow.connect(
        ica_output,
        "thresh_zstat_files",
        feature_spatial_prep,
        "in_files",
    )
    workflow.connect(mask_node, mask_field, feature_spatial_prep, "mask_file")

    reg_2_mni, mni2 = build_ref_2_mni(
        workflow=workflow,
        inputnode=inputnode,
        engine=engine,
        synth_config=synth_config,
        test_run=test_run,
        max_cpu=max_cpu,
    )

    if engine == RegistrationEngine.ANTS:
        apply_warp = apply_registration_node(
            name="func2mni",
            engine=RegistrationEngine.ANTS,
            workflow=workflow,
            warp=None,
            moving=[feature_spatial_prep, "out_file"],
            reference=mni2,
            non_linear=True,
            registration_stack=[reg_2_mni, workflow.reg_2_ref],
        )
    else:
        convert_warp = Node(ConvertWarp(), name="func_2_mni_warp")
        convert_warp.long_name = "func to atlas warp combination"
        convert_warp.inputs.reference = mni2
        workflow.connect(
            workflow.reg_2_ref.out_registered_node,
            workflow.reg_2_ref.warp,
            convert_warp,
            "premat",
        )
        workflow.connect(
            reg_2_mni.out_registered_node, reg_2_mni.warp, convert_warp, "warp1"
        )

        apply_warp = apply_registration_node(
            name="func2mni",
            engine=engine,
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
    workflow.connect(ica_output, "mel_mix", feature_time_series, "mel_mix")

    feature_frequency = Node(FeatureFrequency(), name="feature_frequency")
    workflow.connect(getTR, "TR", feature_frequency, "TR")
    workflow.connect(ica_output, "mel_ft_mix", feature_frequency, "mel_ft_mix")

    aroma_classification = Node(AromaClassification(), name="aroma_classification")
    workflow.connect(feature_frequency, "HFC", aroma_classification, "HFC")
    workflow.connect(
        feature_time_series, "max_rp_corr", aroma_classification, "max_rp_corr"
    )
    workflow.connect(feature_spatial, "csf_fract", aroma_classification, "csf_fract")
    workflow.connect(feature_spatial, "edge_fract", aroma_classification, "edge_fract")

    return aroma_classification, reg_2_mni
