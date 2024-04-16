from nipype.interfaces.freesurfer import ReconAll
from nipype.interfaces.fsl import BinaryMaths
from multiprocessing import cpu_count
from nipype.pipeline.engine import Node
from math import trunc
from swane.nipype_pipeline.nodes.utils import getn
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SegmentHA import SegmentHA
from swane.nipype_pipeline.nodes.CustomLabel2Vol import CustomLabel2Vol
from swane.nipype_pipeline.nodes.ThrROI import ThrROI
from swane.config.config_enums import CORE_LIMIT
from nipype.interfaces.utility import IdentityInterface

FS_DIR = "FS"


def freesurfer_workflow(name: str, is_hippo_amyg_labels: bool, base_dir: str = "/", max_cpu: int = 0,
                        multicore_node_limit: CORE_LIMIT = CORE_LIMIT.SOFT_CAP) -> CustomWorkflow:
    """
    Freesurfer cortical reconstruction, white matter ROI, basal ganglia and thalami ROI.
    If needed, segmentation of the hippocampal substructures and the nuclei of the amygdala.

    Parameters
    ----------
    name : str
        The workflow name.
    is_hippo_amyg_labels : bool
        Enable segmentation of the hippocampal substructures and the nuclei of the amygdala.
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
    wmROI : path
        Binary ROI for cerebral white matter.
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
    
    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=['ref', 'subjects_dir']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['subject_id', 'subjects_dir', 'bgROI', 'wmROI', 'pial', 'white', 'vol_label_file',
                                  'vol_label_file_nii', 'lh_hippoAmygLabels', 'rh_hippoAmygLabels']),
        name='outputnode')

    # NODE 1: Freesurfer cortical reconstruction process
    recon_all = Node(ReconAll(), name='reconAll')
    recon_all.inputs.subject_id = FS_DIR

    # parallel option split some steps in right and left
    if max_cpu > 1:
        recon_all.inputs.parallel = True

    # openmp option apply max cpu tu some steps, resulting in twice cpu usage for rogh/left steps
    if multicore_node_limit == CORE_LIMIT.NO_LIMIT:
        # no limit
        recon_all.inputs.openmp = cpu_count()
    elif multicore_node_limit == CORE_LIMIT.SOFT_CAP:
        # for soft cap we accept that parallelized steps use each max_cpu cores, resulting in twice the setting
        recon_all.inputs.openmp = max_cpu
        recon_all.n_procs = recon_all.inputs.openmp
    else:
        # for hard cap we use half of max_cpu setting, but at least 1
        recon_all.inputs.openmp = max(trunc(max_cpu/2), 1)
        recon_all.n_procs = recon_all.inputs.openmp * 2

    recon_all.inputs.directive = 'all'
    recon_all.inputs.args = "-no-isrunning"
    workflow.add_nodes([recon_all])
    workflow.connect(inputnode, "ref", recon_all, "T1_files")
    workflow.connect(inputnode, "subjects_dir", recon_all, "subjects_dir")

    # NODE 2: Aparcaseg linear transformation in reference space
    aparaseg2Volmgz = Node(CustomLabel2Vol(), name="aparaseg2Volmgz")
    aparaseg2Volmgz.long_name = "label %s to reference space"
    aparaseg2Volmgz.inputs.vol_label_file = "./r-aparc_aseg.mgz"
    workflow.connect(recon_all, "rawavg", aparaseg2Volmgz, "template_file")
    workflow.connect([(recon_all, aparaseg2Volmgz, [(('aparc_aseg', getn, 0), 'reg_header')])])
    workflow.connect([(recon_all, aparaseg2Volmgz, [(('aparc_aseg', getn, 0), 'seg_file')])])
    workflow.connect(recon_all, "subjects_dir", aparaseg2Volmgz, "subjects_dir")
    workflow.connect(recon_all, "subject_id", aparaseg2Volmgz, "subject_id")

    # NODE 3: Aparcaseg conversion mgz -> nifti
    aparaseg2Volnii = Node(CustomLabel2Vol(), name="aparaseg2Volnii")
    aparaseg2Volnii.long_name = "label Nifti conversion"
    aparaseg2Volnii.inputs.vol_label_file = "r-aparc_aseg.nii.gz"
    workflow.connect(recon_all, "rawavg", aparaseg2Volnii, "template_file")
    workflow.connect([(recon_all, aparaseg2Volnii, [(('aparc_aseg', getn, 0), 'reg_header')])])
    workflow.connect([(recon_all, aparaseg2Volnii, [(('aparc_aseg', getn, 0), 'seg_file')])])
    workflow.connect(aparaseg2Volnii, "vol_label_file", outputnode, "vol_label_file_nii")

    # NODE 4: Left cerebral white matter binary ROI
    lhwmROI = Node(ThrROI(), name='lhwmROI')
    lhwmROI.long_name = "Lh white matter ROI"
    lhwmROI.inputs.seg_val_min = 2
    lhwmROI.inputs.seg_val_max = 2
    lhwmROI.inputs.out_file = "lhwmROI.nii.gz"
    workflow.connect(aparaseg2Volnii, "vol_label_file", lhwmROI, "in_file")

    # NODE 5: Right cerebral white matter binary ROI
    rhwmROI = Node(ThrROI(), name='rhwmROI')
    rhwmROI.long_name = "Rh white matter ROI"
    rhwmROI.inputs.seg_val_min = 41
    rhwmROI.inputs.seg_val_max = 41
    rhwmROI.inputs.out_file = "rhwmROI.nii.gz"
    workflow.connect(aparaseg2Volnii, "vol_label_file", rhwmROI, "in_file")

    # NODE 4: Cerebral white matter binary ROI
    wmROI = Node(BinaryMaths(), name='wmROI')
    wmROI.long_name = "white matter ROI"
    wmROI.inputs.operation = "add"
    wmROI.inputs.out_file = "wmROI.nii.gz"
    workflow.connect(lhwmROI, "out_file", wmROI, "in_file")
    workflow.connect(rhwmROI, "out_file", wmROI, "operand_file")

    # NODE 7: Left basal ganglia and thalamus binary ROI
    lhbgROI = Node(ThrROI(), name='lhbgROI')
    lhbgROI.long_name = "Lh Basal ganglia ROI"
    lhbgROI.inputs.seg_val_min = 11
    lhbgROI.inputs.seg_val_max = 13
    lhbgROI.inputs.out_file = "lhbgROI.nii.gz"
    workflow.connect(aparaseg2Volnii, "vol_label_file", lhbgROI, "in_file")

    # NODE 8: Right basal ganglia and thalamus binary ROI
    rhbgROI = Node(ThrROI(), name='rhbgROI')
    rhbgROI.long_name = "Rh Basal ganglia ROI"
    rhbgROI.inputs.seg_val_min = 50
    rhbgROI.inputs.seg_val_max = 52
    rhbgROI.inputs.out_file = "rhbgROI.nii.gz"
    workflow.connect(aparaseg2Volnii, "vol_label_file", rhbgROI, "in_file")

    # NODE 9: Basal ganglia and thalami binary ROI
    bgROI = Node(BinaryMaths(), name='bgROI')
    bgROI.long_name = "Basal ganglia ROI"
    bgROI.inputs.operation = "add"
    bgROI.inputs.out_file = "bgROI.nii.gz"
    workflow.connect(lhbgROI, "out_file", bgROI, "in_file")
    workflow.connect(rhbgROI, "out_file", bgROI, "operand_file")

    workflow.connect(bgROI, "out_file", outputnode, "bgROI")
    # TODO wmROI work in progress - Not used for now. Maybe useful for SUPERFLAIR
    workflow.connect(wmROI, "out_file", outputnode, "wmROI")
    workflow.connect(recon_all, "pial", outputnode, "pial")
    workflow.connect(recon_all, "white", outputnode, "white")
    workflow.connect(recon_all, "subject_id", outputnode, "subject_id")
    workflow.connect(recon_all, "subjects_dir", outputnode, "subjects_dir")
    workflow.connect(aparaseg2Volmgz, "vol_label_file", outputnode, "vol_label_file")

    if is_hippo_amyg_labels:
        # NODE 10: Segmentation of the hippocampal substructures and the nuclei of the amygdala
        segmentHA = Node(SegmentHA(), name="segmentHA")
        if multicore_node_limit == CORE_LIMIT.NO_LIMIT:
            segmentHA.inputs.num_cpu = cpu_count()
        elif multicore_node_limit == CORE_LIMIT.SOFT_CAP:
            segmentHA.inputs.num_cpu = max_cpu
        else:
            segmentHA.inputs.num_cpu = max_cpu
            segmentHA.n_procs = segmentHA.inputs.num_cpu
        workflow.connect(recon_all, "subjects_dir", segmentHA, "subjects_dir")
        workflow.connect(recon_all, "subject_id", segmentHA, "subject_id")
        workflow.connect(segmentHA, "lh_hippoAmygLabels", outputnode, "lh_hippoAmygLabels")
        workflow.connect(segmentHA, "rh_hippoAmygLabels", outputnode, "rh_hippoAmygLabels")

    return workflow
