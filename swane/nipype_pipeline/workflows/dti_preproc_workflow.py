from nipype.interfaces.fsl import (
    ConvertXFM,
    ExtractROI,
    EddyCorrect,
    DTIFit,
    BEDPOSTX5,
)
from nipype.interfaces.freesurfer.utils import LTAConvert
from nipype.pipeline.engine import Node
from swane.config.config_enums import CORE_LIMIT
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.GenEddyFiles import GenEddyFiles
from swane.nipype_pipeline.nodes.CustomEddy import CustomEddy
from swane.nipype_pipeline.nodes.utils import get_deskull_node, get_registration_node, apply_registration_node
from configparser import SectionProxy
from nipype.interfaces.utility import IdentityInterface
from multiprocessing import cpu_count
import os
from os.path import abspath


def dti_preproc_workflow(
    name: str,
    dti_dir: str,
    config: SectionProxy,
    synth_config: SectionProxy,
    base_dir: str = "/",
    max_cpu: int = 0,
    multicore_node_limit: CORE_LIMIT = CORE_LIMIT.SOFT_CAP,
) -> CustomWorkflow:
    """
    DTI preprocessing workflow with eddy current and motion artifact correction.
    Diffusion metrics calculation and, if needed, bayesian estimation of
    diffusion parameters.

    Parameters
    ----------
    name : str
        The workflow name.
    dti_dir : path
        The directory path of DTI dicom files.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    config: SectionProxy
        workflow settings.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings.
    max_cpu : int, optional
        If greater than 0, limit the core usage of bedpostx. The default is 0.
    multicore_node_limit: CORE_LIMIT, optional
        Preference for bedpostX core usage. The default il CORE_LIMIT.SOFT_CAP

    Input Node Fields
    ----------
    reference: path
        T13D reference file.
    reference_brain : path
        Betted T13D reference file.

    Returns
    -------
    workflow : CustomWorkflow
        The DTI preprocessing workflow.

    Output Node Fields
    ----------
    nodiff_mask_file : path
        Brain mask from b0.
    FA : path
        Fractional anysotropy map in reference space.
    fsamples : path
        Samples from the distribution of anysotropic volume fraction.
    phsamples : path
        Samples from the distribution on phi.
    thsamples : path
        Samples from the distribution on theta.
    diff2ref_mat : path
        Linear registration matrix from diffusion to T13D reference space.
    ref2diff_mat : path
        Linear registration inverse matrix from T13D reference to diffusion space.
    mni2ref_warp : path
        Nonlinear registration warp from MNI atlas to T13D reference space.

    """

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(IdentityInterface(fields=["reference_brain", "reference"]), name="inputnode")

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "nodiff_mask_file",
                "FA",
                "fsamples",
                "phsamples",
                "thsamples",
                "diff2ref_mat",
                "ref2diff_mat",
                "mni2ref_warp",
            ]
        ),
        name="outputnode",
    )

    is_cuda = config.getboolean_safe("cuda")

    # NODE 1: Conversion dicom -> nifti
    conversion = Node(CustomDcm2niix(), name="dti_conv")
    conversion.inputs.source_dir = dti_dir
    conversion.inputs.out_filename = "dti"
    conversion.inputs.bids_format = False
    conversion.inputs.request_dti = True
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 1b: Orienting in radiological convention
    reorient = Node(ForceOrient(), name="dti_reOrient")
    workflow.connect(conversion, "converted_files", reorient, "in_file")

    # NODE 2: b0 image extraction
    nodif = Node(ExtractROI(), name="dti_nodif")
    nodif.long_name = "b0 extraction"
    nodif.inputs.t_min = 0
    nodif.inputs.t_size = 1
    nodif.inputs.roi_file = "nodif.nii.gz"
    workflow.connect(reorient, "out_file", nodif, "in_file")

    # NODE 3: Scalp removal from b0 image
    b0_deskull = get_deskull_node(
        name="dti_deskull",
        name_prefix="DTI",
        use_synth=synth_config.getboolean_safe("strip"),
        mask=True,
        bet_thr=0.3,
        bet_robust=True,
        bet_threshold=True,
        out_file="nodif_brain.nii.gz",
    )
    workflow.connect(nodif, "roi_file", b0_deskull, "in_file")

    old_eddy_correct = config.getboolean_safe("old_eddy_correct")
    if old_eddy_correct:
        # NODE 4a: Generate Eddy files
        eddy = Node(EddyCorrect(), name="dti_eddy")
        eddy.inputs.ref_num = 0
        eddy._mem_gb = 1
        eddy.inputs.out_file = "data.nii.gz"
        workflow.connect(reorient, "out_file", eddy, "in_file")
        eddy_output_name = "eddy_corrected"
    else:
        # NODE 4a: Generate Eddy files
        eddy_files = Node(GenEddyFiles(), name="dti_eddy_files")
        workflow.connect(conversion, "bvals", eddy_files, "bval")

        # NODE 4: Eddy current and motion artifact correction
        eddy = Node(CustomEddy(), name="dti_eddy")
        eddy.inputs.use_cuda = is_cuda
        eddy._mem_gb = 1
        if not is_cuda:
            if multicore_node_limit == CORE_LIMIT.HARD_CAP:
                eddy_cpu = max_cpu
                eddy.inputs.num_threads = max_cpu
            elif multicore_node_limit == CORE_LIMIT.SOFT_CAP:
                eddy_cpu = max_cpu
            else:
                eddy_cpu = cpu_count()
            eddy.inputs.environ = {
                "OMP_NUM_THREADS": str(eddy_cpu),
                "FSL_SKIP_GLOBAL": "1",
            }
            eddy.inputs.args = "--nthr=%d" % eddy_cpu

        workflow.connect(reorient, "out_file", eddy, "in_file")
        workflow.connect(conversion, "bvals", eddy, "in_bval")
        workflow.connect(conversion, "bvecs", eddy, "in_bvec")
        workflow.connect(eddy_files, "acqp", eddy, "in_acqp")
        workflow.connect(eddy_files, "index", eddy, "in_index")
        workflow.connect(b0_deskull, "mask_file", eddy, "in_mask")
        eddy_output_name = "out_corrected"

    # NODE 5: DTI metrics calculation
    dtifit = Node(DTIFit(), name="dti_dtifit")
    dtifit.long_name = "DTI metrics calculation"
    workflow.connect(eddy, eddy_output_name, dtifit, "dwi")
    workflow.connect(b0_deskull, "mask_file", dtifit, "mask")
    workflow.connect(conversion, "bvecs", dtifit, "bvecs")
    workflow.connect(conversion, "bvals", dtifit, "bvals")

    # NODE 6: b0 image linear registration in reference space
    dif2ref = get_registration_node(
        name="dif2ref",
        name_prefix="DTI",
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        moving=[nodif, "roi_file"],
        moving_brain=[b0_deskull, "out_file"],
        reference=[inputnode, "reference"],
        flirt_cost="corratio",
        non_linear=False,
        inverse=True,
    )

    # Output mat must be fsl format to be used directly in probtrackx
    if synth_config.getboolean_safe("morph"):
        dif2ref_xfm = Node(LTAConvert(), name="dif2ref_xfm")
        dif2ref_xfm.long_name = "Matrix conversion"
        dif2ref_xfm.inputs.out_fsl = "dif2ref.mat"
        workflow.connect(dif2ref.out_registered_node, dif2ref.warp, dif2ref_xfm, "in_lta")

        ref2dif_xfm = Node(LTAConvert(), name="ref2dif_xfm")
        ref2dif_xfm.long_name = "Inverse matrix conversion"
        ref2dif_xfm.inputs.out_fsl = "ref2dif.mat"
        workflow.connect(dif2ref.inv_warp_node, dif2ref.inv_warp, ref2dif_xfm, "in_lta")

        workflow.connect(dif2ref_xfm, "out_fsl", outputnode, "diff2ref_mat")
        workflow.connect(ref2dif_xfm, "out_fsl", outputnode, "ref2diff_mat")
    else:
        workflow.connect(dif2ref.out_registered_node, dif2ref.warp, outputnode, "diff2ref_mat")
        workflow.connect(dif2ref.inv_warp_node, dif2ref.inv_warp, outputnode, "ref2diff_mat")

    fa_2_ref = apply_registration_node(
        name="fa_2_ref",
        name_prefix="FA",
        name_suffix="to reference",
        use_synth=synth_config.getboolean_safe("morph"),
        workflow=workflow,
        warp=[dif2ref.out_registered_node, dif2ref.warp],
        moving=[dtifit, "FA"],
        reference=[inputnode, "reference"],
        out_file="r-FA.nii.gz",
        non_linear=False,
    )

    workflow.connect(fa_2_ref, "out_file", outputnode, "FA")

    is_tractography = config.getboolean_safe("tractography")
    if is_tractography:

        mni = abspath(os.path.join(os.environ["FSLDIR"], "data/standard/MNI152_T1_1mm.nii.gz"))
        mni_brain = abspath(os.path.join(os.environ["FSLDIR"], "data/standard/MNI152_T1_1mm_brain.nii.gz"))

        mni_2_ref = get_registration_node(
            name="mni_2_ref",
            name_prefix="MNI atlas",
            name_suffix="to reference",
            use_synth=synth_config.getboolean_safe("morph"),
            workflow=workflow,
            moving=mni,
            moving_brain=mni_brain,
            reference=[inputnode, "reference"],
            reference_brain=[inputnode, "reference_brain"],
            flirt_cost="corratio",
            non_linear=True
        )
        workflow.connect(mni_2_ref.out_registered_node, mni_2_ref.warp, outputnode, "mni2ref_warp")

        # NODE 8: Bayesian estimation of diffusion parameters
        bedpostx = Node(BEDPOSTX5(), name="dti_bedpostx")
        bedpostx.inputs.n_fibres = 2
        bedpostx.inputs.rician = True
        bedpostx.inputs.sample_every = 25
        bedpostx.inputs.n_jumps = 1250
        bedpostx.inputs.burn_in = 1000
        bedpostx.inputs.use_gpu = is_cuda
        if not is_cuda:
            # if cuda is enabled only 1 process is launched
            if multicore_node_limit == CORE_LIMIT.SOFT_CAP:
                bedpostx.inputs.environ = {"FSLSUB_PARALLEL": str(max_cpu)}
            elif multicore_node_limit == CORE_LIMIT.HARD_CAP:
                bedpostx.inputs.environ = {"FSLSUB_PARALLEL": str(max_cpu)}
                bedpostx.n_procs = max_cpu

        workflow.connect(eddy, eddy_output_name, bedpostx, "dwi")
        workflow.connect(b0_deskull, "mask_file", bedpostx, "mask")
        workflow.connect(conversion, "bvecs", bedpostx, "bvecs")
        workflow.connect(conversion, "bvals", bedpostx, "bvals")

        workflow.connect(bedpostx, "merged_fsamples", outputnode, "fsamples")
        workflow.connect(b0_deskull, "mask_file", outputnode, "nodiff_mask_file")
        workflow.connect(bedpostx, "merged_phsamples", outputnode, "phsamples")
        workflow.connect(bedpostx, "merged_thsamples", outputnode, "thsamples")

    return workflow
