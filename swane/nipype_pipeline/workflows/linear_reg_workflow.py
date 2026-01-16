from nipype.interfaces.fsl import RobustFOV, ApplyMask
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from nipype import Node
from nipype.interfaces.utility import IdentityInterface, Function
from configparser import SectionProxy
from swane.nipype_pipeline.nodes.utils import (
    get_deskull_node,
    get_registration_node,
    apply_registration_node,
)


def linear_reg_workflow(
    name: str,
    dicom_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    is_volumetric: bool = True,
    is_partial_coverage: bool = False,
) -> CustomWorkflow:
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
    synth_config: SectionProxy
        FreeSurfer Synth tools settings.
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
    reference_brain : path
        The reference brain image for the registration.
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
    registered_file_brain : string
        Output betted file in T13D reference space.
    out_matrix_file : path
        Linear registration matrix to T13D reference space.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(
            fields=["reference", "reference_brain", "output_name", "brain_mask"]
        ),
        name="inputnode",
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=["registered_file", "registered_file_brain" "out_matrix_file"]
        ),
        name="outputnode",
    )

    # NODE 1: Conversion dicom -> nifti
    conversion = Node(CustomDcm2niix(), name="%s_conv" % name)
    conversion.inputs.source_dir = dicom_dir
    conversion.inputs.bids_format = False
    conversion.inputs.out_filename = name
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 2: Orienting in radiological convention
    reorient = Node(ForceOrient(), name="%s_reorient" % name)
    workflow.connect(conversion, "converted_files", reorient, "in_file")

    # NODE 3: Crop neck
    robustfov = Node(RobustFOV(), name="%s_robustfov" % name)
    workflow.connect(reorient, "out_file", robustfov, "in_file")

    def get_betted_name(basename):
        return "r-%s_brain.nii.gz" % basename

    betted_name = Node(
        Function(
            input_names=["basename"],
            output_names=["out_file"],
            function=get_betted_name,
        ),
        name="betted_name",
    )
    betted_name.long_name = "Registered file name"
    workflow.connect(inputnode, "output_name", betted_name, "basename")

    def get_unbetted_name(basename):
        return "r-%s.nii.gz" % basename

    unbetted_name = Node(
        Function(
            input_names=["basename"],
            output_names=["out_file"],
            function=get_unbetted_name,
        ),
        name="unbetted_name",
    )
    unbetted_name.long_name = "Deskulled registered file name"
    workflow.connect(inputnode, "output_name", unbetted_name, "basename")

    bet_thr = None if not config else config.getfloat_safe("bet_thr")
    bet_bias_correction = (
        False if not config else config.getboolean_safe("bet_bias_correction")
    )
    flirt_search = 90
    reference_brain = [inputnode, "reference_brain"]

    if is_partial_coverage:
        moving_brain = [robustfov, "out_roi"]
        flirt_search = 40
        reference_brain = [inputnode, "reference"]
    else:
        deskull = get_deskull_node(
            name=name + "_deskull",
            name_prefix=name,
            use_synth=synth_config.getboolean_safe("strip"),
            mask=True,
            bet_thr=bet_thr,
            bet_robust=True,
            bet_bias_correction=bet_bias_correction,
        )
        workflow.connect(robustfov, "out_roi", deskull, "in_file")
        moving_brain = [deskull, "out_file"]

    reg_wrap = get_registration_node(
        name=name,
        name_prefix=name,
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        moving=[robustfov, "out_roi"],
        moving_brain=moving_brain,
        reference=[inputnode, "reference"],
        reference_brain=reference_brain,
        is_volumetric=is_volumetric,
        out_file=[unbetted_name, "out_file"],
        flirt_cost="mutualinfo",
        flirt_search=flirt_search,
    )

    if is_partial_coverage:
        brain_masking = Node(ApplyMask(), name="%s_brain_mask" % name)
        brain_masking.long_name = "Brain %s"
        workflow.connect(
            reg_wrap.out_registered_node,
            reg_wrap.out_registered_image,
            brain_masking,
            "in_file",
        )
        workflow.connect(betted_name, "out_file", brain_masking, "out_file")
        workflow.connect(inputnode, "brain_mask", brain_masking, "mask_file")
        workflow.connect(brain_masking, "out_file", outputnode, "registered_file_brain")
    else:
        deskull_2_ref = apply_registration_node(
            name=name,
            name_prefix="Skull stripped image",
            name_suffix="to reference",
            use_synth=synth_config.getboolean_safe("morph"),
            workflow=workflow,
            warp=[reg_wrap.out_registered_node, reg_wrap.warp],
            moving=[deskull, "out_file"],
            reference=[inputnode, "reference"],
            out_file=[betted_name, "out_file"],
            non_linear=False,
        )
        workflow.connect(deskull_2_ref, "out_file", outputnode, "registered_file_brain")

    workflow.connect(
        reg_wrap.out_registered_node,
        reg_wrap.out_registered_image,
        outputnode,
        "registered_file",
    )
    workflow.connect(
        reg_wrap.out_registered_node, reg_wrap.warp, outputnode, "out_matrix_file"
    )

    return workflow
