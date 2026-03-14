from nipype.interfaces.fsl import (
    Split,
    ApplyMask,
    ImageStats,
    ImageMaths,
)
from nipype.interfaces.utility import Merge
from nipype.pipeline.engine import Node
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.VenousCheck import VenousCheck
from nipype.interfaces.utility import IdentityInterface
from configparser import SectionProxy
from swane.nipype_pipeline.nodes.utils import get_deskull_node
from swane.nipype_pipeline.nodes.utils import (
    apply_registration_node,
    get_registration_node,
)


def venous_mr_workflow(
    name: str,
    venous_mr_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    venous2_mr_dir: str = None,
    base_dir: str = "/",
) -> CustomWorkflow:
    """
    Analysis of phase contrasts images (in single or two series) to obtain in skull veins
    in reference space, scaled in 0-100 value.

    Parameters
    ----------
    name : str
        The workflow name.
    venous_mr_dir : path
        The directory path of the venous phase contrast DICOM files.
    config: SectionProxy
        workflow settings.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings.
    venous2_mr_dir : path
        If veins phase is divided from anatomic phase, use this param to load the second DICOM files directory.
    base_dir : str, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    reference : path
        T13D.
    reference_brain : path
        Betted T13D.

    Returns
    -------
    workflow : CustomWorkflow
        The venous workflow.

    Output Node Fields
    ----------
    veins : path
        Intracranial veins in T13D reference space.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference_brain", "reference"]), name="inputnode"
    )

    # Output Node
    outputnode = Node(IdentityInterface(fields=["veins"]), name="outputnode")

    # NODE 1a: Conversion dicom -> nifti
    veins_conv = Node(CustomDcm2niix(), name="veins_conv")
    veins_conv.inputs.source_dir = venous_mr_dir
    veins_conv.inputs.bids_format = False
    veins_conv.inputs.out_filename = "veins"
    veins_conv.inputs.name_conflicts = 1
    veins_conv.inputs.merge_imgs = 2

    # NODE 2a: Orienting in radiological convention
    veins_reOrient = Node(ForceOrient(), name="veins_reOrient")
    workflow.connect(veins_conv, "converted_files", veins_reOrient, "in_file")

    # NODE 4: Detect the venous phase from the anatomic phase
    veins_check = Node(VenousCheck(), name="veins_check")
    veins_check.long_name = "angiographic volume detection"
    vein_detection_mode = config.getenum_safe("vein_detection_mode")
    veins_check.inputs.detection_mode = vein_detection_mode
    # If the phases are in the same sequence
    if venous2_mr_dir is None:
        # NODE 3a: Divide the two phases from the phase contrast
        veins_split = Node(Split(), name="veins_split")
        veins_split.long_name = "volumes splitting"
        veins_split.inputs.dimension = "t"
        workflow.connect(veins_reOrient, "out_file", veins_split, "in_file")

        workflow.connect(veins_split, "out_files", veins_check, "in_files")
    else:
        # NODE 1b: Conversion dicom -> nifti
        veins2_conv = Node(CustomDcm2niix(), name="veins2_conv")
        veins2_conv.inputs.source_dir = venous2_mr_dir
        veins2_conv.inputs.bids_format = False
        veins2_conv.inputs.out_filename = "veins2"
        veins2_conv.inputs.name_conflicts = 1
        veins2_conv.inputs.merge_imgs = 2

        # NODE 2b: Orienting in radiological convention
        veins2_reOrient = Node(ForceOrient(), name="veins2_reOrient")
        workflow.connect(veins2_conv, "converted_files", veins2_reOrient, "in_file")

        # NODE 3b: Merge the two phases
        veins_merge = Node(Merge(2), name="veins_merge")
        veins_merge.long_name = "volumes merging"
        workflow.connect(veins_reOrient, "out_file", veins_merge, "in1")
        workflow.connect(veins2_reOrient, "out_file", veins_merge, "in2")

        workflow.connect(veins_merge, "out", veins_check, "in_files")

    # NODE 5: Scalp removal and in skull structures segmentation
    deskull = get_deskull_node(
        name_prefix="anatomic phase",
        name="vein_mr_deskull",
        use_synth=synth_config.getboolean_safe("strip"),
        mask=True,
        bet_thr=config.getfloat_safe("bet_thr"),
        bet_surfaces=True,
    )
    workflow.connect(veins_check, "out_file_anat", deskull, "in_file")

    # NODE 6: Apply in skull mask to venous phase
    veins_inskull_mask = Node(ApplyMask(), name="veins_inskull_mask")
    veins_inskull_mask.long_name = "%s inskull veins"
    workflow.connect(veins_check, "out_file_veins", veins_inskull_mask, "in_file")
    workflow.connect(deskull, deskull.inskull_out_name, veins_inskull_mask, "mask_file")

    # NODE 7: Linear registration of anatomic phase to reference space
    # NODE 8: Linear transformation of in skull venous phase in reference space

    anat_2_ref = get_registration_node(
        name="anat_2_ref",
        name_prefix="anatomic phase",
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        moving=[veins_check, "out_file_anat"],
        moving_brain=[veins_check, "out_file_anat"],
        reference=[inputnode, "reference"],
        reference_brain=[inputnode, "reference_brain"],
        flirt_cost="mutualinfo",
    )

    veins_2_ref = apply_registration_node(
        name_prefix="venous phase",
        name_suffix="to reference",
        name="veins_2_ref",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[anat_2_ref.out_registered_node, anat_2_ref.warp],
        moving=[veins_inskull_mask, "out_file"],
        reference=[inputnode, "reference"],
        non_linear=False,
    )

    # NODE 9: Get the max value of venous phase
    veins_range = Node(ImageStats(), name="veins_range")
    veins_range.long_name = "intensity range detection"
    veins_range.inputs.op_string = "-R"
    workflow.connect(veins_2_ref, "out_file", veins_range, "in_file")

    # NODE 10: Venous phase rescaling in 0-100
    veins_rescale = Node(ImageMaths(), name="veins_rescale")
    veins_rescale.long_name = "intensity normalization"
    veins_rescale.inputs.out_file = "r-veins_mra_inskull.nii.gz"

    # Function to define the operation string
    def rescale_string(intensity_range):
        op_string = "-mul 100 -div %f" % intensity_range[1]
        return op_string

    workflow.connect(
        veins_range, ("out_stat", rescale_string), veins_rescale, "op_string"
    )
    workflow.connect(veins_2_ref, "out_file", veins_rescale, "in_file")

    workflow.connect(veins_rescale, "out_file", outputnode, "veins")

    return workflow
