from configparser import SectionProxy

import swane_supplement

from nipype.interfaces.fsl import (
    ApplyMask,
    BinaryMaths,
    FAST,
    ImageStats,
    SpatialFilter,
    Threshold,
)
from nipype.pipeline.engine import Node
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.ThrROI import ThrROI
from nipype.interfaces.utility import IdentityInterface, Function
from swane.nipype_pipeline.nodes.utils import apply_registration_node


def flat1_workflow(
    name: str, mni1_dir: str, synth_config: SectionProxy, base_dir: str = "/"
) -> CustomWorkflow:
    """
    Creation of a junction and extension z-score map based on T13D, FLAIR3D and
    a mean template.

    Parameters
    ----------
    name : str
        The workflow name.
    mni1_dir : path
        The file path of the MNI1 template.
    synth_config: SectionProxy
        reeSurfer Synth tools settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    reference_brain : path
        Betted T13D reference file.
    flair_brain : path
        Betted FLAIR3D.
    ref_2_mni1_warp : path
        Nonlinear registration warp from T13D reference space to MNI1 atlas.
    ref_2_mni1_inverse_warp : path
        Nonlinear registration inverse warp from MNI1 atlas space to T13D reference.

    Returns
    -------
    workflow : CustomWorkflow
        The FLAT1 workflow.

    Output Node Fields
    ----------
    extension_z : path
        Extension z-score map in T13D reference space.
        Based on:
        - Pascher et al. - Automated morphometric MRI analysis for the detection of PNH - Epilepsia 2013
    junction_z : path
        Junction z-score map in T13D reference space.
        Based on:
        - Huppertz et al. - Enhanced visualization of blurred gray-white matter junctions in focal cortical
                            dysplasia by voxel-based 3D MRI analysis - Epilepsy Res 2005
        - Huppertz et al. - Voxel-based 3D MRI analysis helps to detect subtle forms of subcortical band
                            heterotopia - Epilepsia 2008
    binary_flair : path
        Divided image FLAIR/T13D.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(
            fields=[
                "reference_brain",
                "flair_brain",
                "ref_2_mni1_warp",
                "ref_2_mni1_inverse_warp",
            ]
        ),
        name="inputnode",
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(fields=["extension_z", "junction_z", "binary_flair"]),
        name="outputnode",
    )

    # NODE 1: three class fast segmentation
    fast = Node(FAST(), name="%s_fast" % name, mem_gb=4)
    fast.inputs.img_type = 1  # param -t
    fast.inputs.number_classes = 3  # param n
    fast.inputs.hyper = 0.1  # param -H
    fast.inputs.bias_lowpass = 40  # param -l
    fast.inputs.output_biascorrected = True  # param -B
    fast.inputs.bias_iters = 4  # param -I
    workflow.add_nodes([fast])
    workflow.connect(inputnode, "reference_brain", fast, "in_files")

    def pick_first_two(file_list):
        return file_list[1], file_list[2]

    fast_segment_split = Node(
        Function(
            input_names=["file_list"],
            output_names=["gm_seg", "wm_seg"],
            function=pick_first_two,
        ),
        name="fast_segment_split",
    )
    fast_segment_split.long_name = "Segment identification"
    workflow.connect(fast, "partial_volume_files", fast_segment_split, "file_list")

    flair_2_mni1 = apply_registration_node(
        name="flair_2_mni1",
        name_prefix="flair",
        name_suffix="MNI atlas",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_warp"],
        moving=[inputnode, "flair_brain"],
        reference=mni1_dir,
        non_linear=True,
    )

    restore_2_mni1 = apply_registration_node(
        name="restore_2_mni1",
        name_prefix="T1",
        name_suffix="MNI atlas",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_warp"],
        moving=[fast, "restored_image"],
        reference=mni1_dir,
        non_linear=True,
    )

    gm_2_mni1 = apply_registration_node(
        name="gm_2_mni1",
        name_prefix="Gray matter",
        name_suffix="MNI atlas",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_warp"],
        moving=[fast_segment_split, "gm_seg"],
        reference=mni1_dir,
        non_linear=True,
    )

    wm_2_mni1 = apply_registration_node(
        name="wm_2_mni1",
        name_prefix="White matter",
        name_suffix="MNI atlas",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_warp"],
        moving=[fast_segment_split, "wm_seg"],
        reference=mni1_dir,
        non_linear=True,
    )

    # NODE 6: Divided image generation from FLAIR/T1
    flair_div_ref = Node(BinaryMaths(), name="%s_flairDIVref" % name)
    flair_div_ref.long_name = "Flair/T1 normalization"
    flair_div_ref.inputs.operation = "div"
    workflow.connect(flair_2_mni1, "out_file", flair_div_ref, "in_file")
    workflow.connect(restore_2_mni1, "out_file", flair_div_ref, "operand_file")

    # Remove the upper 1% of values to trim values from incorrect registration
    outliers_removal = Node(Threshold(), name="%s_outliers_mask" % name)
    outliers_removal.long_name = "Outliers removal"
    outliers_removal.inputs.thresh = 98
    outliers_removal.inputs.use_robust_range = True
    outliers_removal.inputs.use_nonzero_voxels = True
    outliers_removal.inputs.direction = "above"
    workflow.connect(flair_div_ref, "out_file", outliers_removal, "in_file")

    # NODE 8: Cerebellum removal from divided image
    cortex_mask = Node(ApplyMask(), name="%s_cortexMask" % name)
    cortex_mask.long_name = "outliers %s"
    cortex_mask.inputs.mask_file = swane_supplement.cortex_mas
    workflow.connect(outliers_removal, "out_file", cortex_mask, "in_file")

    # NODE 9: Masking for gray matter on t1_restore in MNI1
    gm_mask = Node(ApplyMask(), name="%s_gmMask" % name)
    gm_mask.long_name = "Grey matter %s"
    workflow.connect(cortex_mask, "out_file", gm_mask, "in_file")
    workflow.connect(gm_2_mni1, "out_file", gm_mask, "mask_file")

    # NODE 10: Masking for white matter on t1_restore in MNI1
    wm_mask = Node(ApplyMask(), name="%s_wmMask" % name)
    wm_mask.long_name = "White matter %s"
    workflow.connect(cortex_mask, "out_file", wm_mask, "in_file")
    workflow.connect(wm_2_mni1, "out_file", wm_mask, "mask_file")

    # NODE 11: Mean calculation for gray matter
    gm_mean = Node(ImageStats(), name="%s_gm_mean" % name)
    gm_mean.long_name = "Grey matter mean value calculation"
    gm_mean.inputs.op_string = "-M"
    workflow.connect(gm_mask, "out_file", gm_mean, "in_file")

    # NODE 12: Mean calculation for white matter
    wm_mean = Node(ImageStats(), name="%s_wm_mean" % name)
    wm_mean.long_name = "White matter mean value calculation"
    wm_mean.inputs.op_string = "-M"
    workflow.connect(wm_mask, "out_file", wm_mean, "in_file")

    # TODO parametri per ora inutilizzati. Valutare in futuro la loro implementazione
    # FLAT1_gm_std = Node(ImageStats(), name="%s_gm_std")
    # FLAT1_gm_std.inputs.op_string="-S"
    # workflow.connect(FLAT1_gmMask,"out_file",FLAT1_gm_std,"in_file")

    # FLAT1_wm_std = Node(ImageStats(), name="%s_wm_std")
    # FLAT1_wm_std.inputs.op_string="-S"
    # workflow.connect(FLAT1_wmMask,"out_file",FLAT1_wm_std,"in_file")

    # NODE 13: Mask generation with values between mean white matter and mean gray matter values
    binary_flair = Node(ThrROI(), name="%s_binaryFLAIR" % name)
    binary_flair.long_name = "Mean based masking"
    binary_flair.inputs.out_file = "binary_flair.nii.gz"
    workflow.connect(cortex_mask, "out_file", binary_flair, "in_file")
    workflow.connect(gm_mean, "out_stat", binary_flair, "seg_val_max")
    workflow.connect(wm_mean, "out_stat", binary_flair, "seg_val_min")

    # NODE 14: Junction map generation
    convolution_flair = Node(SpatialFilter(), name="%s_convolution_flair" % name)
    convolution_flair.long_name = "junction map generation"
    convolution_flair.inputs.operation = "mean"  # Param -fmean
    convolution_flair.inputs.kernel_shape = "boxv"  # Param -kernel
    convolution_flair.inputs.kernel_size = 5  # Param -kernel value
    convolution_flair.inputs.out_file = "convolution_flair.nii.gz"
    workflow.connect(binary_flair, "out_file", convolution_flair, "in_file")

    # NODE 13: Junction map mean value calculation
    junction_mean = Node(BinaryMaths(), name="%s_junction_mean" % name)
    junction_mean.long_name = "junction variation from mean atlas"
    junction_mean.inputs.operation = "sub"  # Param -sub
    junction_mean.inputs.operand_file = swane_supplement.mean_flair
    junction_mean.inputs.out_file = "junction_flair.nii.gz"
    workflow.connect(convolution_flair, "out_file", junction_mean, "in_file")

    # NODE 14: Junction z-score calculation
    junction_z = Node(BinaryMaths(), name="%s_junctionz" % name)
    junction_z.long_name = "junction z score calculation"
    junction_z.inputs.operation = "div"
    junction_z.inputs.operand_file = swane_supplement.std_final_flair
    junction_z.inputs.out_file = "junctionZ_flair.nii.gz"
    workflow.connect(junction_mean, "out_file", junction_z, "in_file")

    # NODE 15: Cerebellum mask on restore_t1
    masked_cerebellum = Node(ApplyMask(), name="%s_masked_cerebellum" % name)
    masked_cerebellum.long_name = "cerebellum %s"
    masked_cerebellum.inputs.mask_file = swane_supplement.binary_cerebellum
    workflow.connect(restore_2_mni1, "out_file", masked_cerebellum, "in_file")

    # NODE 16: Cerebellum mean value calculation
    cerebellum_mean = Node(ImageStats(), name="%s_cerebellum_mean" % name)
    cerebellum_mean.long_name = "cerebellum mean value calculation"
    cerebellum_mean.inputs.op_string = "-M"
    workflow.connect(masked_cerebellum, "out_file", cerebellum_mean, "in_file")

    # NODE 17: Grey matter mask on restore_t1
    restore_gm_mask = Node(ApplyMask(), name="%s_restore_gmMask" % name)
    restore_gm_mask.long_name = "grey matter %s"
    restore_gm_mask.inputs.out_file = "masked_image_GM.nii.gz"
    workflow.connect(restore_2_mni1, "out_file", restore_gm_mask, "in_file")
    workflow.connect(gm_2_mni1, "out_file", restore_gm_mask, "mask_file")

    # NODE 18: Grey matter normalization on cerebellum mean value
    normalised_gm_mask = Node(BinaryMaths(), name="%s_normalised_GM_mask" % name)
    normalised_gm_mask.long_name = "Grey matter/cerebellum normalization"
    normalised_gm_mask.inputs.operation = "div"
    normalised_gm_mask.inputs.out_file = "normalised_GM_mask.nii.gz"
    workflow.connect(restore_gm_mask, "out_file", normalised_gm_mask, "in_file")
    workflow.connect(cerebellum_mean, "out_stat", normalised_gm_mask, "operand_value")

    # NODE 19: Extension map generation
    smoothed_image_extension = Node(
        SpatialFilter(), name="%s_smoothed_image_extension" % name
    )
    smoothed_image_extension.long_name = "extension map generation"
    smoothed_image_extension.inputs.operation = "mean"  # Param -fmean
    smoothed_image_extension.inputs.kernel_shape = "boxv"  # Param -kernel
    smoothed_image_extension.inputs.kernel_size = 5  # Param -kernel value
    smoothed_image_extension.inputs.out_file = "smoothed_image_extension.nii.gz"
    workflow.connect(
        normalised_gm_mask, "out_file", smoothed_image_extension, "in_file"
    )

    # NODE 20: Extension map mean value calculation
    extension_mean = Node(BinaryMaths(), name="%s_image_extension" % name)
    extension_mean.long_name = "extension variation from mean atlas"
    extension_mean.inputs.operation = "sub"
    extension_mean.inputs.operand_file = swane_supplement.mean_extension
    extension_mean.inputs.out_file = "extension_image.nii.gz"
    workflow.connect(smoothed_image_extension, "out_file", extension_mean, "in_file")

    # NODE 21: Extension z-score calculation
    extension_z = Node(BinaryMaths(), name="%s_image_extensionz" % name)
    extension_z.long_name = "extension z score calculation"
    extension_z.inputs.operation = "div"
    extension_z.inputs.operand_file = swane_supplement.std_final_extension
    extension_z.inputs.out_file = "extension_z.nii.gz"
    workflow.connect(extension_mean, "out_file", extension_z, "in_file")

    # NODE 22: Cerebellum removal from extension z-score map
    no_cereb_extension_z = Node(ApplyMask(), name="%s_no_cereb_extension_z" % name)
    no_cereb_extension_z.long_name = "cerebellum %s"
    no_cereb_extension_z.inputs.out_file = "no_cereb_extension_z.nii.gz"
    workflow.connect(extension_z, "out_file", no_cereb_extension_z, "in_file")
    # workflow.connect(outliers_mask, "out_file", no_cereb_extension_z, "mask_file")
    no_cereb_extension_z.inputs.mask_file = swane_supplement.cortex_mas

    extension_z_2_ref = apply_registration_node(
        name="extension_z_2_ref",
        name_prefix="Extension",
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_inverse_warp"],
        moving=[no_cereb_extension_z, "out_file"],
        reference=[inputnode, "reference_brain"],
        non_linear=True,
        out_file="r-extension_z.nii.gz",
    )

    junction_z_2_ref = apply_registration_node(
        name="junction_z_2_ref",
        name_prefix="Junction",
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_inverse_warp"],
        moving=[junction_z, "out_file"],
        reference=[inputnode, "reference_brain"],
        non_linear=True,
        out_file="r-junction_z.nii.gz",
    )

    binary_flair_2_ref = apply_registration_node(
        name="binary_flair_2_ref",
        name_prefix="Binary Flair",
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[inputnode, "ref_2_mni1_inverse_warp"],
        moving=[binary_flair, "out_file"],
        reference=[inputnode, "reference_brain"],
        non_linear=True,
        out_file="r-binary_flair.nii.gz",
    )

    workflow.connect(extension_z_2_ref, "out_file", outputnode, "extension_z")
    workflow.connect(junction_z_2_ref, "out_file", outputnode, "junction_z")
    workflow.connect(binary_flair_2_ref, "out_file", outputnode, "binary_flair")

    return workflow
