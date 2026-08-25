from nipype.interfaces.fsl import (
    ApplyMask,
    ImageMaths,
    Threshold,
    ErodeImage,
    DilateImage,
    BinaryMaths,
)
from nipype import Node, IdentityInterface
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from configparser import SectionProxy

from swane.config.config_enums import CoreLimit, RegistrationEngine
from swane.nipype_pipeline.nodes.utils import (
    get_registration_node,
    resolve_registration_engine,
)


def seeg_ct_workflow(
    name: str,
    seeg_ct_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    max_cpu: int = 0,
    multicore_node_limit: CoreLimit = CoreLimit.SOFT_CAP,
    test_run: bool = False,
) -> CustomWorkflow:
    """
    Analysis of CT after stereoEGG to extract elecrtodes.

    Parameters
    ----------
    name : str
        The workflow name.
    seeg_ct_dir : path
        The directory path of the no contrast scan DICOM files.
    config: SectionProxy
        workflow settings.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings (drives the registration engine).
    base_dir : str, optional
        The base directory path relative to parent workflow. The default is "/".
    max_cpu : int, optional
        If greater than 0, limit the core usage of the registration tools. The
        default is 0.
    multicore_node_limit : CoreLimit, optional
        Preference for the registration tools core usage. The default is
        CoreLimit.SOFT_CAP.
    test_run : bool, optional
        If True, speed up the underlying registration for prerelease test
        runs at the cost of accuracy. The default is False.

    Input Node Fields
    ----------
    reference : path
        T13D.
    reference_brain : path
        Betted T13D.
    brain_mask : path
        Brain mask.

    Returns
    -------
    workflow : CustomWorkflow
        The venous workflow.

    Output Node Fields
    ----------
    electrodes : path
        Intracranial veins in T13D reference space.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # CT follows the global registration engine (ANTs by default). The former
    # scientific FSL pin (``# FLIRT performs better on CT``) is lifted so CT
    # exercises ANTs, and the comparative oracle validates it on real data.
    # SynthMorph is the known-worse backend on CT, so an explicit SynthMorph
    # choice falls back to FSL; an ANTs config stays ANTs (that is the point of
    # this work), and an explicit FSL choice stays FSL.
    engine = resolve_registration_engine(synth_config, allow_ants=True)
    if engine == RegistrationEngine.SYNTH:
        engine = RegistrationEngine.FSL

    electrode_thr = config.getint_safe("electrode_threshold")
    erode_kernel_size = config.getfloat_safe("erode_kernel_size")

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference_brain", "reference", "brain_mask"]),
        name="inputnode",
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(fields=["electrodes", "mat"]), name="outputnode"
    )

    # NODE 1: Conversion dicom -> nifti
    seeg_ct_conv = Node(CustomDcm2niix(), name="seeg_ct_conv")
    seeg_ct_conv.inputs.source_dir = seeg_ct_dir
    seeg_ct_conv.inputs.bids_format = False
    seeg_ct_conv.inputs.out_filename = "seeg_ct"
    seeg_ct_conv.inputs.name_conflicts = 1
    seeg_ct_conv.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    seeg_ct_reOrient = Node(ForceOrient(), name="seeg_ct_reOrient")
    workflow.connect(seeg_ct_conv, "converted_files", seeg_ct_reOrient, "in_file")

    # TODO: wiki reference for electrode masking weight https://pmc.ncbi.nlm.nih.gov/articles/PMC10670384/

    # NODE 3: Weight map generation
    electrodes_weight_map = Node(ImageMaths(), name="electrodes_weight_bin")
    electrodes_weight_map.long_name = "Electrode weight map for registration"
    electrodes_weight_map.inputs.op_string = (
        "-thr %.10f -bin -mul -1 -add 1" % electrode_thr
    )
    workflow.connect(seeg_ct_reOrient, "out_file", electrodes_weight_map, "in_file")

    # Linear registration of the seeg CT to reference space. The binary weight
    # map (0 on electrodes, 1 elsewhere) down-weights the metal artefact around
    # the electrodes: the abstraction wires it as the ANTs metric ``moving_mask``
    # (1 marks the region the metric registers ON) or, on FSL, as FLIRT's
    # ``in_weight`` -- the same map, correct polarity for both.
    seeg_ct_2_ref = get_registration_node(
        name="seeg_ct_2_ref",
        name_prefix="",
        name_suffix="to reference space",
        engine=engine,
        workflow=workflow,
        moving=[seeg_ct_reOrient, "out_file"],
        reference=[inputnode, "reference"],
        non_linear=False,
        is_volumetric=True,
        flirt_cost="mutualinfo",
        flirt_search=90,
        moving_mask=[electrodes_weight_map, "out_file"],
        test_run=test_run,
        max_cpu=max_cpu,
        multicore_node_limit=multicore_node_limit,
        limit_synth_cores=synth_config.getboolean_safe("limit_cores"),
    )
    seeg_registered_node = seeg_ct_2_ref.registered_node
    seeg_registered_field = seeg_ct_2_ref.registered_field

    # Electrode mask in ref space
    seeg_electrodes_thr_ref = Node(Threshold(), name="seeg_electrodes_thr_ref")
    seeg_electrodes_thr_ref.long_name = "Electrode segmentation"
    seeg_electrodes_thr_ref.inputs.thresh = electrode_thr
    workflow.connect(
        seeg_registered_node, seeg_registered_field, seeg_electrodes_thr_ref, "in_file"
    )

    # No electode mask in ref space
    seeg_no_electrodes_thr_ref = Node(Threshold(), name="seeg_no_electrodes_thr_ref")
    seeg_no_electrodes_thr_ref.long_name = "Brain segmentation"
    seeg_no_electrodes_thr_ref.inputs.thresh = electrode_thr
    seeg_no_electrodes_thr_ref.inputs.direction = "above"
    workflow.connect(
        seeg_registered_node,
        seeg_registered_field,
        seeg_no_electrodes_thr_ref,
        "in_file",
    )

    # Erode brain mask
    ref_brain_erode = Node(ErodeImage(), name="ref_brain_erode")
    ref_brain_erode.long_name = "Erode brain mask borders"
    ref_brain_erode.inputs.kernel_shape = "box"
    ref_brain_erode.inputs.kernel_size = erode_kernel_size
    workflow.connect(inputnode, "brain_mask", ref_brain_erode, "in_file")

    # Dilate brain mask
    ref_brain_dilate = Node(DilateImage(), name="ref_brain_dilate")
    ref_brain_dilate.long_name = "Dilate brain mask borders"
    ref_brain_dilate.inputs.operation = "mean"
    # ref_brain_dilate.inputs.kernel_size = 3
    workflow.connect(inputnode, "brain_mask", ref_brain_dilate, "in_file")

    # Mask seeg ct
    seeg_ct_brain = Node(ApplyMask(), name="seeg_ct_brain")
    seeg_ct_brain.long_name = "Brain %s"
    workflow.connect(seeg_no_electrodes_thr_ref, "out_file", seeg_ct_brain, "in_file")
    workflow.connect(ref_brain_erode, "out_file", seeg_ct_brain, "mask_file")

    # Mask electrode at near-skull dimension
    seeg_ct_electrode_skull = Node(ApplyMask(), name="seeg_ct_electrode_skull")
    seeg_ct_electrode_skull.long_name = "Skull %s"
    workflow.connect(
        seeg_electrodes_thr_ref, "out_file", seeg_ct_electrode_skull, "in_file"
    )
    workflow.connect(ref_brain_dilate, "out_file", seeg_ct_electrode_skull, "mask_file")

    # Add outskull elecrode in
    seeg_electodes = Node(BinaryMaths(), name="seeg_electodes")
    seeg_electodes.long_name = "Electrodes+brain image calculation"
    seeg_electodes.inputs.out_file = "r-seeg_electrodes.nii.gz"
    seeg_electodes.inputs.operation = "add"
    workflow.connect(seeg_ct_brain, "out_file", seeg_electodes, "in_file")
    workflow.connect(
        seeg_ct_electrode_skull, "out_file", seeg_electodes, "operand_file"
    )

    workflow.connect(seeg_electodes, "out_file", outputnode, "electrodes")

    return workflow
