from nipype.interfaces.fsl import (
    BET,
    FLIRT,
    ConvertXFM,
    ExtractROI,
    EddyCorrect,
    DTIFit,
    ApplyXFM,
    FNIRT,
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
from swane.nipype_pipeline.nodes.SynthMorphReg import SynthMorphReg
from swane.nipype_pipeline.nodes.SynthMorphApply import SynthMorphApply
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from configparser import SectionProxy
from nipype.interfaces.utility import IdentityInterface
from multiprocessing import cpu_count
from swane.utils.DependencyManager import DependencyManager
import os
from os.path import abspath


def dti_preproc_workflow(
    name: str,
    dti_dir: str,
    config: SectionProxy,
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
    max_cpu : int, optional
        If greater than 0, limit the core usage of bedpostx. The default is 0.
    multicore_node_limit: CORE_LIMIT, optional
        Preference for bedpostX core usage. The default il CORE_LIMIT.SOFT_CAP

    Input Node Fields
    ----------
    ref: path
        T13D reference file.
    ref_brain : path
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
    inputnode = Node(IdentityInterface(fields=["ref_brain", "ref"]), name="inputnode")

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
    if DependencyManager.is_freesurfer_synth():
        b0_deskull = Node(SynthStrip(), name="%s_synthstrip" % name, mem_gb=5)
        b0_deskull.inputs.mask_file = "nodif_brain_mask.nii.gz"
        workflow.connect(nodif, "roi_file", b0_deskull, "in_file")
    else:
        b0_deskull = Node(BET(), name="nodif_BET")
        b0_deskull.inputs.frac = 0.3
        b0_deskull.inputs.robust = True
        b0_deskull.inputs.threshold = True
        b0_deskull.inputs.mask = True
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
    if DependencyManager.is_freesurfer_synth():
        dif2ref = Node(SynthMorphReg(), name="diff2ref_synthreg", mem_gb=9)
        dif2ref.long_name = "%s to reference space"
        dif2ref.long_name = "%s to reference space"
        dif2ref.inputs.model = "affine"
        workflow.connect(nodif, "roi_file", dif2ref, "in_file")
        workflow.connect(inputnode, "ref", dif2ref, "reference")

        fa_2_ref = Node(SynthMorphApply(), name="FA2ref_synthapp")
        fa_2_ref.long_name = "FA %s in reference space"
        workflow.connect(dtifit, "FA", fa_2_ref, "in_file")
        workflow.connect(dif2ref, "warp_file", fa_2_ref, "warp_file")

        diff2ref_xfm = Node(LTAConvert(), name="diff2ref_xfm")
        diff2ref_xfm.long_name = "Transformation matrix conversion"
        diff2ref_xfm.inputs.out_fsl = "diff2ref.mat"
        workflow.connect(dif2ref, "warp_file", diff2ref_xfm, "in_lta")

        ref2diff_xfm = Node(LTAConvert(), name="ref2diff_xfm")
        ref2diff_xfm.long_name = "Inverse transformation matrix conversion"
        ref2diff_xfm.inputs.out_fsl = "ref2diff.mat"
        workflow.connect(dif2ref, "inv_warp_file", ref2diff_xfm, "in_lta")

        workflow.connect(fa_2_ref, "out_file", outputnode, "FA")
        workflow.connect(diff2ref_xfm, "out_fsl", outputnode, "diff2ref_mat")
        workflow.connect(ref2diff_xfm, "out_fsl", outputnode, "ref2diff_mat")
    else:
        dif2ref = Node(FLIRT(), name="diff2ref_FLIRT")
        dif2ref.long_name = "%s to reference space"
        dif2ref.inputs.out_matrix_file = "diff2ref.mat"
        dif2ref.inputs.cost = "corratio"
        dif2ref.inputs.searchr_x = [-90, 90]
        dif2ref.inputs.searchr_y = [-90, 90]
        dif2ref.inputs.searchr_z = [-90, 90]
        dif2ref.inputs.dof = 6
        workflow.connect(b0_deskull, "out_file", dif2ref, "in_file")
        workflow.connect(inputnode, "ref_brain", dif2ref, "reference")

        # NODE 7: FA linear transformation in reference space
        fa_2_ref = Node(ApplyXFM(), name="FA2ref_FLIRT")
        fa_2_ref.long_name = "FA %s in reference space"
        fa_2_ref.inputs.out_file = "r-FA.nii.gz"
        fa_2_ref.inputs.interp = "trilinear"
        workflow.connect(dtifit, "FA", fa_2_ref, "in_file")
        workflow.connect(dif2ref, "out_matrix_file", fa_2_ref, "in_matrix_file")
        workflow.connect(inputnode, "ref_brain", fa_2_ref, "reference")

        # NODE 9: Linear transformation inverse matrix calculation from diffusion to reference space
        ref2diff_convert = Node(ConvertXFM(), name="ref2diff_convert")
        ref2diff_convert.long_name = "inverse transformation from reference space"
        ref2diff_convert.inputs.invert_xfm = True
        ref2diff_convert.inputs.out_file = "ref2diff.mat"
        workflow.connect(dif2ref, "out_matrix_file", ref2diff_convert, "in_file")

        workflow.connect(fa_2_ref, "out_file", outputnode, "FA")
        workflow.connect(dif2ref, "out_matrix_file", outputnode, "diff2ref_mat")
        workflow.connect(ref2diff_convert, "out_file", outputnode, "ref2diff_mat")

    is_tractography = config.getboolean_safe("tractography")

    if is_tractography:
        if DependencyManager.is_freesurfer_synth():
            mni_2_ref = Node(SynthMorphReg(), name="mni_2_ref_synthreg", mem_gb=13)
            mni_2_ref.long_name = "%s to atlas space"
            mni_2_ref.inputs.model = "joint"
            mni_dir = abspath(
                os.path.join(os.environ["FSLDIR"], "data/standard/MNI152_T1_1mm.nii.gz")
            )
            mni_2_ref.inputs.in_file = mni_dir
            workflow.connect(inputnode, "ref", mni_2_ref, "reference")

            workflow.connect(mni_2_ref, "warp_file", outputnode, "mni2ref_warp")
        else:
            # NODE 1: Linear registration
            mni_2_ref_flirt = Node(FLIRT(), name="mni_2_ref_flirt")
            mni_2_ref_flirt.long_name = "atlas %s to diffusion space"
            mni_2_ref_flirt.inputs.searchr_x = [-90, 90]
            mni_2_ref_flirt.inputs.searchr_y = [-90, 90]
            mni_2_ref_flirt.inputs.searchr_z = [-90, 90]
            mni_2_ref_flirt.inputs.dof = 12
            mni_2_ref_flirt.inputs.cost = "corratio"
            mni_2_ref_flirt.inputs.out_matrix_file = "mni_2_ref.mat"
            mni_dir = abspath(
                os.path.join(
                    os.environ["FSLDIR"], "data/standard/MNI152_T1_2mm_brain.nii.gz"
                )
            )
            mni_2_ref_flirt.inputs.in_file = mni_dir
            workflow.add_nodes([mni_2_ref_flirt])
            workflow.connect(inputnode, "ref_brain", mni_2_ref_flirt, "reference")

            # NODE 2: Nonlinear registration
            mni_2_ref_fnirt = Node(FNIRT(), name="mni_2_ref_fnirt")
            mni_2_ref_fnirt.long_name = "atlas %s to diffusion space"
            mni_2_ref_fnirt.inputs.fieldcoeff_file = True
            mni_2_ref_fnirt.inputs.in_file = mni_dir
            workflow.connect(
                mni_2_ref_flirt, "out_matrix_file", mni_2_ref_fnirt, "affine_file"
            )
            workflow.connect(inputnode, "ref_brain", mni_2_ref_fnirt, "ref_file")

            workflow.connect(
                mni_2_ref_fnirt, "fieldcoeff_file", outputnode, "mni2ref_warp"
            )

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
