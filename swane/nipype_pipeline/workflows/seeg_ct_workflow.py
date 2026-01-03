from nipype.interfaces.fsl import (
    FLIRT,
    ApplyMask,
    ApplyXFM,
    ImageMaths,
    Threshold,
    ErodeImage,
    DilateImage,
    BinaryMaths
)
from nipype import Node, IdentityInterface
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from configparser import SectionProxy
from swane.utils.DependencyManager import DependencyManager

def seeg_ct_workflow(
    name: str,
    seeg_ct_dir: str,
    config: SectionProxy,
    base_dir: str = "/",
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
    base_dir : str, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    ref : path
        T13D.
    ref_brain : path
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
    electrode_thr = config.getint_safe("electrode_threshold")
    erode_kernel_size = config.getfloat_safe("erode_kernel_size")

    # Input Node
    inputnode = Node(IdentityInterface(fields=["ref_brain", "ref", "brain_mask"]), name="inputnode")

    # Output Node
    outputnode = Node(IdentityInterface(fields=["electrodes", "mat"]), name="outputnode")

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
    if DependencyManager.is_freesurfer_synth():
        deskull = Node(SynthStrip(), name="%s_synthstrip" % name, mem_gb=3)
        workflow.connect(seeg_ct_reOrient, "out_file", deskull, "in_file")

        seeg_electrodes_thr = Node(Threshold(), name="seeg_electrodes_thr")
        seeg_electrodes_thr.long_name = "Electrode thresholding"
        seeg_electrodes_thr.inputs.thresh = electrode_thr
        workflow.connect(seeg_ct_reOrient, "out_file", seeg_electrodes_thr, "in_file")

        electrodes_weight_bin = Node(ImageMaths(), name="electrodes_weight_bin")
        electrodes_weight_bin.long_name = "Electrode weight map for registration"
        electrodes_weight_bin.inputs.op_string = "-bin -mul -1 -add 1"
        workflow.connect(seeg_electrodes_thr, "out_file", electrodes_weight_bin, "in_file")

        electrodes_weight_map = Node(ApplyMask(), name="electrodes_weight_map")
        workflow.connect(electrodes_weight_bin, "out_file", electrodes_weight_map, "in_file")
        workflow.connect(deskull, "out_file", electrodes_weight_map, "mask_file")

        # NODE 5: Linear registration to reference space
        seeg_ct_brain_2_ref_flirt = Node(FLIRT(), name="seeg_ct_brain_2_ref_flirt")
        seeg_ct_brain_2_ref_flirt.long_name = "%s to reference space"
        seeg_ct_brain_2_ref_flirt.inputs.out_matrix_file = "seegct2ref.mat"
        seeg_ct_brain_2_ref_flirt.inputs.cost = "mutualinfo"
        seeg_ct_brain_2_ref_flirt.inputs.searchr_x = [-90, 90]
        seeg_ct_brain_2_ref_flirt.inputs.searchr_y = [-90, 90]
        seeg_ct_brain_2_ref_flirt.inputs.searchr_z = [-90, 90]
        seeg_ct_brain_2_ref_flirt.inputs.dof = 6
        seeg_ct_brain_2_ref_flirt.inputs.interp = "trilinear"
        workflow.connect(electrodes_weight_map, "out_file", seeg_ct_brain_2_ref_flirt, "in_weight")
        workflow.connect(deskull, "out_file", seeg_ct_brain_2_ref_flirt, "in_file")
        workflow.connect(inputnode, "ref_brain", seeg_ct_brain_2_ref_flirt, "reference")

        seeg_ct_2_ref_flirt = Node(ApplyXFM(), name="seeg_ct_2_ref_flirt")
        seeg_ct_2_ref_flirt.long_name = "%s to reference space"
        seeg_ct_2_ref_flirt.inputs.interp = "trilinear"
        workflow.connect(seeg_ct_reOrient, "out_file", seeg_ct_2_ref_flirt, "in_file")
        workflow.connect(seeg_ct_brain_2_ref_flirt, "out_matrix_file", seeg_ct_2_ref_flirt, "in_matrix_file")
        workflow.connect(inputnode, "ref", seeg_ct_2_ref_flirt, "reference")

    else:
        electrodes_weight_map = Node(ImageMaths(), name="electrodes_weight_bin")
        electrodes_weight_map.long_name = "Electrode weight map for registration"
        electrodes_weight_map.inputs.op_string = "-thr %.10f -bin -mul -1 -add 1" % electrode_thr
        workflow.connect(seeg_ct_reOrient, "out_file", electrodes_weight_map, "in_file")

        seeg_ct_2_ref_flirt = Node(FLIRT(), name="seeg_ct_2_ref_flirt")
        seeg_ct_2_ref_flirt.long_name = "%s to reference space"
        seeg_ct_2_ref_flirt.inputs.out_matrix_file = "seegct2ref.mat"
        seeg_ct_2_ref_flirt.inputs.cost = "mutualinfo"
        seeg_ct_2_ref_flirt.inputs.searchr_x = [-90, 90]
        seeg_ct_2_ref_flirt.inputs.searchr_y = [-90, 90]
        seeg_ct_2_ref_flirt.inputs.searchr_z = [-90, 90]
        seeg_ct_2_ref_flirt.inputs.dof = 6
        seeg_ct_2_ref_flirt.inputs.interp = "trilinear"
        workflow.connect(electrodes_weight_map, "out_file", seeg_ct_2_ref_flirt, "in_weight")
        workflow.connect(seeg_ct_reOrient, "out_file", seeg_ct_2_ref_flirt, "in_file")
        workflow.connect(inputnode, "ref", seeg_ct_2_ref_flirt, "reference")

    # Electrode mask in ref space
    seeg_electrodes_thr_ref = Node(Threshold(), name="seeg_electrodes_thr_ref")
    seeg_electrodes_thr_ref.long_name = "Electrode thresholding"
    seeg_electrodes_thr_ref.inputs.thresh = electrode_thr
    workflow.connect(seeg_ct_2_ref_flirt, "out_file", seeg_electrodes_thr_ref, "in_file")

    # Erode brain mask
    ref_brain_erode = Node(ErodeImage(), name="ref_brain_erode")
    ref_brain_erode.long_name = "Erode brain mask borders"
    ref_brain_erode.inputs.kernel_shape = "box"
    ref_brain_erode.inputs.kernel_size = erode_kernel_size
    workflow.connect(inputnode, "brain_mask", ref_brain_erode, "in_file")

    # Dilate brain mask
    ref_brain_dilate = Node(ErodeImage(), name="ref_brain_dilate")
    ref_brain_dilate.long_name = "Dilate brain mask borders"
    ref_brain_dilate.inputs.kernel_shape = "box"
    ref_brain_dilate.inputs.kernel_size = 3
    workflow.connect(inputnode, "brain_mask", ref_brain_dilate, "in_file")

    # Mask seeg ct
    seeg_ct_brain = Node(ApplyMask(), name="seeg_ct_brain")
    seeg_ct_brain.long_name = "Brain %s"
    workflow.connect(seeg_ct_2_ref_flirt, "out_file", seeg_ct_brain, "in_file")
    workflow.connect(ref_brain_erode, "out_file", seeg_ct_brain, "mask_file")

    # Mask electrode at near-skull dimension
    seeg_ct_electrode_skull = Node(ApplyMask(), name="seeg_ct_electrode_skull")
    seeg_ct_electrode_skull.long_name = "Skull %s"
    workflow.connect(seeg_electrodes_thr_ref, "out_file", seeg_ct_electrode_skull, "in_file")
    workflow.connect(ref_brain_dilate, "out_file", seeg_ct_electrode_skull, "mask_file")

    seeg_ct_brain_no_elecrode = Node(ApplyMask(), name="seeg_ct_brain_no_elecrode")
    seeg_ct_brain_no_elecrode.long_name = "Electrode %s"
    workflow.connect(seeg_ct_brain, "out_file", seeg_ct_brain_no_elecrode, "in_file")
    workflow.connect(seeg_electrodes_thr_ref, "out_file", seeg_ct_brain_no_elecrode, "mask_file")

    # Add outskull elecrode in
    seeg_electodes = Node(BinaryMaths(), name="seeg_electodes")
    seeg_electodes.long_name = "Electrodes+brain image calculation"
    seeg_electodes.inputs.out_file = "r-seeg_electrodes.nii.gz"
    seeg_electodes.inputs.operation = "add"
    workflow.connect(seeg_ct_brain_no_elecrode, "out_file", seeg_electodes, "in_file")
    workflow.connect(seeg_ct_electrode_skull, "out_file", seeg_electodes, "operand_file")

    workflow.connect(seeg_electodes, "out_file", outputnode, "electrodes")

    return workflow
