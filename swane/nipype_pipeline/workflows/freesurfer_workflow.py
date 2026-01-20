from configparser import SectionProxy

from nipype.interfaces.freesurfer import ReconAll, ApplyVolTransform
from nipype.interfaces.fsl import BinaryMaths
from multiprocessing import cpu_count
from nipype.pipeline.engine import Node
from math import trunc

from swane.nipype_pipeline.nodes.SynthSeg import SynthSeg
from swane.nipype_pipeline.nodes.utils import getn
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SegmentHA import SegmentHA
from swane.nipype_pipeline.nodes.ThrROI import ThrROI
from swane.config.config_enums import CORE_LIMIT, FREESURFER_STEP
from nipype.interfaces.utility import IdentityInterface
from swane.utils.ResourceManager import ResourceManager

FS_DIR = "FS"


def freesurfer_workflow(
    name: str,
    step: FREESURFER_STEP,
    is_hippo_amyg_labels: bool,
    synth_config: SectionProxy,
    base_dir: str = "/",
    max_cpu: int = 0,
    multicore_node_limit: CORE_LIMIT = CORE_LIMIT.SOFT_CAP,
) -> CustomWorkflow:
    """
    Freesurfer cortical reconstruction, white matter ROI, basal ganglia and thalami ROI.
    If needed, segmentation of the hippocampal substructures and the nuclei of the amygdala.

    Parameters
    ----------
    name : str
        The workflow name.
    step : FREESURFER_STEP
        Step to be executed.
    is_hippo_amyg_labels : bool
        Enable segmentation of the hippocampal substructures and the nuclei of the amygdala.
    synth_config: SectionProxy
        FreeSurfer Synth tools settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".
    max_cpu : int, optional
        If greater than 0, limit the core usage of bedpostx. The default is 0.
    multicore_node_limit: CORE_LIMIT, optional
        Preference for bedpostX core usage. The default il CORE_LIMIT.SOFT_CAP

    Input Node Fields
    ----------
    ref : path
        T13D reference file.
    subjects_dir : path
        Directory for Freesurfer analysis.

    Returns
    -------
    workflow : CustomWorkflow
        The Freesurfer workflow.

    Output Node Fields
    ----------
    subject_id : string
        Subject name for Freesurfer (defined as FS_DIR="FS").
    subjects_dir : path
        Directory for Freesurfer analysis.
    bgROI : path
        Binary ROI for basal ganglia and thalamus.
    pial : list of strings
        Gray matter/pia mater rh and lh surfaces.
    white : list of strings
        White/gray matter rh and lh surfaces.
    vol_label_file : path
        Aparc parcellation projected into aseg volume in reference space.
    vol_label_file_nii : path
        Aparc parcellation projected into aseg volume in reference space and nifti format.
    lh_hippoAmygLabels : path
        Left side labels from segmentation of the hippocampal substructures and the nuclei of the amygdala.
    rh_hippoAmygLabels : path
        Right side labels from segmentation of the hippocampal substructures and the nuclei of the amygdala.

    """

    if step == FREESURFER_STEP.DISABLED:
        # This should not be possible
        return None

    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=["reference", "subjects_dir"]), name="inputnode"
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "subject_id",
                "subjects_dir",
                "bgROI",
                "pial",
                "white",
                "vol_label_file",
                "vol_label_file_nii",
                "lh_hippoAmygLabels",
                "rh_hippoAmygLabels",
            ]
        ),
        name="outputnode",
    )

    # Utility node to handle different paths of segmentation
    segmentation_holder = Node(
        IdentityInterface(fields=["seg_nii"]), name="segmentation_holder"
    )

    if step == FREESURFER_STEP.SYNTHSEG:
        synth_seg = Node(SynthSeg(), name="synth_seg")
        synth_seg.inputs.parcellation = True
        synth_seg.inputs.robust = True
        synth_seg.inputs.use_cpu = True
        synth_seg.inputs.keep_geometry = True
        synth_seg.inputs.num_threads = 1
        synth_seg.inputs.out_file = "r-aparc_aseg.mgz"
        workflow.connect(inputnode, "reference", synth_seg, "in_file")
        workflow.connect(synth_seg, "out_file", outputnode, "vol_label_file")

        # NODE 3: Aparcaseg conversion mgz -> nifti
        synth_seg2nii = Node(ApplyVolTransform(), name="synth_seg2nii")
        synth_seg2nii.long_name = "Parcellation Nifti conversion"
        synth_seg2nii.inputs.transformed_file = "seg.nii.gz"
        synth_seg2nii.inputs.reg_header = True
        synth_seg2nii.inputs.interp = "nearest"
        workflow.connect(synth_seg, "out_file", synth_seg2nii, "source_file")
        workflow.connect(inputnode, "reference", synth_seg2nii, "target_file")
        workflow.connect(
            synth_seg2nii, "transformed_file", outputnode, "vol_label_file_nii"
        )
        workflow.connect(
            synth_seg2nii, "transformed_file", segmentation_holder, "seg_nii"
        )
    else:
        # Resources setup
        reconall_mem_gb = 5
        reconall_environ = {}
        reconall_parallel = False
        reconall_openmp = 1
        reconall_nprocs = 1

        if synth_config.getboolean_safe("reconall"):
            reconall_mem_gb = (
                ResourceManager.synth_reconall_ram_requirements()
            )  # new recon-all needs a lot of RAM
            # New reconall may heavily increase RAM usage with more than 1 cpu, for now skip openmp if using synth tools
        else:
            reconall_environ = {"FS_V8_XOPTS": "0"}
            # parallel option splits some steps in right and left
            if max_cpu > 1:
                reconall_parallel = True
            # openmp option apply max cpu tu some steps, resulting in twice cpu usage for rogh/left steps
            if multicore_node_limit == CORE_LIMIT.NO_LIMIT:
                # no limit
                reconall_openmp = cpu_count()
            elif multicore_node_limit == CORE_LIMIT.SOFT_CAP:
                # for soft cap we accept that parallelized steps use each max_cpu cores, resulting in twice the setting
                reconall_openmp = max_cpu
                reconall_nprocs = reconall_openmp
            elif max_cpu > 1:
                # for hard cap we use half of max_cpu setting, but at least 1
                reconall_openmp = max(trunc(max_cpu / 2), 1)
                reconall_nprocs = reconall_openmp * 2

        # NODE 1: Freesurfer autorecon1
        recon_all_recon1 = Node(ReconAll(), name="recon_all_recon1")
        recon_all_recon1.long_name = "%s: Preprocessing"
        recon_all_recon1.inputs.subject_id = FS_DIR
        recon_all_recon1._mem_gb = reconall_mem_gb
        recon_all_recon1.inputs.environ = reconall_environ
        recon_all_recon1.inputs.parallel = reconall_parallel
        recon_all_recon1.inputs.openmp = reconall_openmp
        recon_all_recon1.n_procs = reconall_nprocs
        recon_all_recon1.inputs.directive = "autorecon1"
        recon_all_recon1.inputs.args = "-no-isrunning"
        workflow.connect(inputnode, "reference", recon_all_recon1, "T1_files")
        workflow.connect(inputnode, "subjects_dir", recon_all_recon1, "subjects_dir")

        workflow.connect(recon_all_recon1, "subject_id", outputnode, "subject_id")
        workflow.connect(recon_all_recon1, "subjects_dir", outputnode, "subjects_dir")

        # NODE 2: Freesurfer autorecon2
        recon_all_recon2 = Node(ReconAll(), name="recon_all_recon2")
        recon_all_recon2.long_name = "%s: Subcortical Segmentation"
        recon_all_recon2._mem_gb = reconall_mem_gb
        recon_all_recon2.inputs.environ = reconall_environ
        recon_all_recon2.inputs.parallel = reconall_parallel
        recon_all_recon2.inputs.openmp = reconall_openmp
        recon_all_recon2.n_procs = reconall_nprocs
        recon_all_recon2.inputs.directive = "autorecon2"
        recon_all_recon2.inputs.args = "-no-isrunning"
        workflow.connect(
            recon_all_recon1, "subjects_dir", recon_all_recon2, "subjects_dir"
        )
        workflow.connect(recon_all_recon1, "subject_id", recon_all_recon2, "subject_id")

        if step in [FREESURFER_STEP.AUTORECON_PIAL, FREESURFER_STEP.RECONALL]:
            # NODE 2: Freesurfer autorecon2
            recon_all_recon_pial = Node(ReconAll(), name="recon_all_recon_pial")
            recon_all_recon_pial.long_name = "%s: Surfaces + Cortical Parcellationn"
            recon_all_recon_pial._mem_gb = reconall_mem_gb
            recon_all_recon_pial.inputs.environ = reconall_environ
            recon_all_recon_pial.inputs.parallel = reconall_parallel
            recon_all_recon_pial.inputs.openmp = reconall_openmp
            recon_all_recon_pial.n_procs = reconall_nprocs
            recon_all_recon_pial.inputs.directive = "autorecon-pial"
            recon_all_recon_pial.inputs.args = "-no-isrunning"
            workflow.connect(
                recon_all_recon2, "subjects_dir", recon_all_recon_pial, "subjects_dir"
            )
            workflow.connect(
                recon_all_recon2, "subject_id", recon_all_recon_pial, "subject_id"
            )

            workflow.connect(recon_all_recon_pial, "pial", outputnode, "pial")
            workflow.connect(recon_all_recon_pial, "white", outputnode, "white")

            # NODE 2: Aparcaseg linear transformation in reference space
            aparc_aseg2ref = Node(ApplyVolTransform(), name="aparc_aseg2ref")
            aparc_aseg2ref.long_name = "Parcellation Nifti conversion"
            aparc_aseg2ref.inputs.transformed_file = "r-aparc_aseg.mgz"
            aparc_aseg2ref.inputs.reg_header = True
            aparc_aseg2ref.inputs.interp = "nearest"
            workflow.connect(
                [
                    (
                        recon_all_recon_pial,
                        aparc_aseg2ref,
                        [(("aparc_aseg", getn, 0), "source_file")],
                    )
                ]
            )
            workflow.connect(inputnode, "reference", aparc_aseg2ref, "target_file")
            workflow.connect(
                aparc_aseg2ref, "transformed_file", outputnode, "vol_label_file"
            )

            aparc_aseg2nii = Node(ApplyVolTransform(), name="aparc_aseg2nii")
            aparc_aseg2nii.long_name = "Parcellation Nifti conversion"
            aparc_aseg2nii.inputs.transformed_file = "r-aparc_aseg.nii.gz"
            aparc_aseg2nii.inputs.reg_header = True
            aparc_aseg2nii.inputs.interp = "nearest"
            workflow.connect(
                [
                    (
                        recon_all_recon_pial,
                        aparc_aseg2nii,
                        [(("aparc_aseg", getn, 0), "source_file")],
                    )
                ]
            )
            workflow.connect(inputnode, "reference", aparc_aseg2nii, "target_file")
            workflow.connect(
                aparc_aseg2nii, "transformed_file", outputnode, "vol_label_file_nii"
            )
            workflow.connect(
                aparc_aseg2nii, "transformed_file", segmentation_holder, "seg_nii"
            )

        else:
            segmentation_holder = None

        if step == FREESURFER_STEP.RECONALL:
            recon_all_recon3 = Node(ReconAll(), name="reconAll")
            recon_all_recon3.long_name = "%s: Complete"
            recon_all_recon3._mem_gb = reconall_mem_gb
            recon_all_recon3.inputs.environ = reconall_environ
            recon_all_recon3.inputs.parallel = reconall_parallel
            recon_all_recon3.inputs.openmp = reconall_openmp
            recon_all_recon3.n_procs = reconall_nprocs
            recon_all_recon3.inputs.directive = "autorecon3"
            recon_all_recon3.inputs.args = "-no-isrunning"
            workflow.connect(
                recon_all_recon_pial, "subjects_dir", recon_all_recon3, "subjects_dir"
            )
            workflow.connect(
                recon_all_recon_pial, "subject_id", recon_all_recon3, "subject_id"
            )

        if is_hippo_amyg_labels:
            # NODE 10: Segmentation of the hippocampal substructures and the nuclei of the amygdala
            segment_ha = Node(SegmentHA(), name="segment_ha")
            segment_ha._mem_gb = 5
            if multicore_node_limit == CORE_LIMIT.NO_LIMIT:
                segment_ha.inputs.num_cpu = cpu_count()
            elif multicore_node_limit == CORE_LIMIT.SOFT_CAP:
                segment_ha.inputs.num_cpu = max_cpu
            else:
                segment_ha.inputs.num_cpu = max_cpu
                segment_ha.n_procs = segment_ha.inputs.num_cpu
            workflow.connect(
                recon_all_recon2, "subjects_dir", segment_ha, "subjects_dir"
            )
            workflow.connect(recon_all_recon2, "subject_id", segment_ha, "subject_id")
            workflow.connect(
                segment_ha, "lh_hippoAmygLabels", outputnode, "lh_hippoAmygLabels"
            )
            workflow.connect(
                segment_ha, "rh_hippoAmygLabels", outputnode, "rh_hippoAmygLabels"
            )

    if segmentation_holder is not None:
        # NODE 7: Left basal ganglia and thalamus binary ROI
        lhbgROI = Node(ThrROI(), name="lhbgROI")
        lhbgROI.long_name = "Lh Basal ganglia ROI"
        lhbgROI.inputs.seg_val_min = 11
        lhbgROI.inputs.seg_val_max = 13
        lhbgROI.inputs.out_file = "lhbgROI.nii.gz"
        workflow.connect(segmentation_holder, "seg_nii", lhbgROI, "in_file")

        # NODE 8: Right basal ganglia and thalamus binary ROI
        rhbgROI = Node(ThrROI(), name="rhbgROI")
        rhbgROI.long_name = "Rh Basal ganglia ROI"
        rhbgROI.inputs.seg_val_min = 50
        rhbgROI.inputs.seg_val_max = 52
        rhbgROI.inputs.out_file = "rhbgROI.nii.gz"
        workflow.connect(segmentation_holder, "seg_nii", rhbgROI, "in_file")

        # NODE 9: Basal ganglia and thalami binary ROI
        bgROI = Node(BinaryMaths(), name="bgROI")
        bgROI.long_name = "Basal ganglia ROI"
        bgROI.inputs.operation = "add"
        bgROI.inputs.out_file = "bgROI.nii.gz"
        workflow.connect(lhbgROI, "out_file", bgROI, "in_file")
        workflow.connect(rhbgROI, "out_file", bgROI, "operand_file")

        workflow.connect(bgROI, "out_file", outputnode, "bgROI")

        # TODO wmROI work in progress - Not used for now. Maybe useful for SUPERFLAIR
        # # NODE 4: Left cerebral white matter binary ROI
        # lhwmROI = Node(ThrROI(), name="lhwmROI")
        # lhwmROI.long_name = "Lh white matter ROI"
        # lhwmROI.inputs.seg_val_min = 2
        # lhwmROI.inputs.seg_val_max = 2
        # lhwmROI.inputs.out_file = "lhwmROI.nii.gz"
        # workflow.connect(segmentation_holder, "seg_nii", lhwmROI, "in_file")
        #
        # # NODE 5: Right cerebral white matter binary ROI
        # rhwmROI = Node(ThrROI(), name="rhwmROI")
        # rhwmROI.long_name = "Rh white matter ROI"
        # rhwmROI.inputs.seg_val_min = 41
        # rhwmROI.inputs.seg_val_max = 41
        # rhwmROI.inputs.out_file = "rhwmROI.nii.gz"
        # workflow.connect(segmentation_holder, "seg_nii", rhwmROI, "in_file")
        #
        # # NODE 4: Cerebral white matter binary ROI
        # wmROI = Node(BinaryMaths(), name="wmROI")
        # wmROI.long_name = "white matter ROI"
        # wmROI.inputs.operation = "add"
        # wmROI.inputs.out_file = "wmROI.nii.gz"
        # workflow.connect(lhwmROI, "out_file", wmROI, "in_file")
        # workflow.connect(rhwmROI, "out_file", wmROI, "operand_file")
        # workflow.connect(wmROI, "out_file", outputnode, "wmROI")

    return workflow
