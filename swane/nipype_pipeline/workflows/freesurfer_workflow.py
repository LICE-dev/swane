from nipype.interfaces.freesurfer import ReconAll
from nipype.interfaces.fsl import BinaryMaths

from nipype.pipeline.engine import Node

from swane.nipype_pipeline.nodes.utils import getn
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.SegmentHA import SegmentHA
from swane.nipype_pipeline.nodes.CustomLabel2Vol import CustomLabel2Vol
from swane.nipype_pipeline.nodes.ThrROI import ThrROI

from nipype.interfaces.utility import IdentityInterface

FS_DIR = "FS"


def freesurfer_workflow(name: str, is_hippo_amyg_labels: bool, base_dir: str = "/")  -> CustomWorkflow:
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
        
    Input Node Fields
    ----------
    max_node_cpu : int
        Max number of cpu to use for the workflow.
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
    bgtROI : path
        Binary ROI for basal ganglia and thalamus.
    wmROI : path
        Binary ROI for cerebral white matter.
    pial : list of strings
        Gray matter/pia mater rh and lh surfaces.
    white : list of strings
        White/gray matter rh and lh surfaces.
    vol_label_file : path
        Aparc parcellation projected into aseg volume in reference space.
    lh_hippoAmygLabels : path
        Left side labels from segmentation of the hippocampal substructures and the nuclei of the amygdala.
    rh_hippoAmygLabels : path
        Right side labels from segmentation of the hippocampal substructures and the nuclei of the amygdala.

    """
    
    workflow = CustomWorkflow(name=name, base_dir=base_dir)

    # Input Node
    inputnode = Node(
        IdentityInterface(fields=['max_node_cpu', 'ref', 'subjects_dir']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['subject_id', 'subjects_dir', 'bgtROI', 'wmROI',
                                  'pial', 'white', 'vol_label_file', 'lh_hippoAmygLabels',
                                  'rh_hippoAmygLabels']),
        name='outputnode')

    # NODE 1: Freesurfer cortical reconstruction process
    reconAll = Node(ReconAll(), name='reconAll')
    reconAll.inputs.subject_id = FS_DIR
    reconAll.inputs.parallel = True
    reconAll.inputs.directive = 'all'
    workflow.add_nodes([reconAll])
    workflow.connect(inputnode, "max_node_cpu", reconAll, "openmp")
    workflow.connect(inputnode, "ref", reconAll, "T1_files")
    workflow.connect(inputnode, "subjects_dir", reconAll, "subjects_dir")

    # NODE 2: Aparcaseg linear transformation in reference space
    aparaseg2Volmgz = Node(CustomLabel2Vol(), name="aparaseg2Volmgz")
    aparaseg2Volmgz.long_name = "label %s to reference space"
    aparaseg2Volmgz.inputs.vol_label_file = "./r-aparc_aseg.mgz"
    workflow.connect(reconAll, "rawavg", aparaseg2Volmgz, "template_file")
    workflow.connect([(reconAll, aparaseg2Volmgz, [(('aparc_aseg', getn, 0), 'reg_header')])])
    workflow.connect([(reconAll, aparaseg2Volmgz, [(('aparc_aseg', getn, 0), 'seg_file')])])
    workflow.connect(reconAll, "subjects_dir", aparaseg2Volmgz, "subjects_dir")
    workflow.connect(reconAll, "subject_id", aparaseg2Volmgz, "subject_id")

    # NODE 3: Aparcaseg conversion mgz -> nifti
    aparaseg2Volnii = Node(CustomLabel2Vol(), name="aparaseg2Volnii")
    aparaseg2Volnii.long_name = "label Nifti conversion"
    aparaseg2Volnii.inputs.vol_label_file = "r-aparc_aseg.nii.gz"
    workflow.connect(reconAll, "rawavg", aparaseg2Volnii, "template_file")
    workflow.connect([(reconAll, aparaseg2Volnii, [(('aparc_aseg', getn, 0), 'reg_header')])])
    workflow.connect([(reconAll, aparaseg2Volnii, [(('aparc_aseg', getn, 0), 'seg_file')])])

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
    lhbgtROI = Node(ThrROI(), name='lhbgtROI')
    lhbgtROI.long_name = "Lh BGT ROI"
    lhbgtROI.inputs.seg_val_min = 10
    lhbgtROI.inputs.seg_val_max = 13
    lhbgtROI.inputs.out_file = "lhbgtROI.nii.gz"
    workflow.connect(aparaseg2Volnii, "vol_label_file", lhbgtROI, "in_file")

    # NODE 8: Right basal ganglia and thalamus binary ROI
    rhbgtROI = Node(ThrROI(), name='rhbgtROI')
    rhbgtROI.long_name = "Rh BGT ROI"
    rhbgtROI.inputs.seg_val_min = 49
    rhbgtROI.inputs.seg_val_max = 52
    rhbgtROI.inputs.out_file = "rhbgtROI.nii.gz"
    workflow.connect(aparaseg2Volnii, "vol_label_file", rhbgtROI, "in_file")

    # NODE 9: Basal ganglia and thalami binary ROI
    bgtROI = Node(BinaryMaths(), name='bgtROI')
    bgtROI.long_name = "BGT ROI"
    bgtROI.inputs.operation = "add"
    bgtROI.inputs.out_file = "bgtROI.nii.gz"
    workflow.connect(lhbgtROI, "out_file", bgtROI, "in_file")
    workflow.connect(rhbgtROI, "out_file", bgtROI, "operand_file")

    workflow.connect(bgtROI, "out_file", outputnode, "bgtROI")
    # TODO wmROI work in progress - Not used for now. Maybe useful for SUPERFLAIR
    workflow.connect(wmROI, "out_file", outputnode, "wmROI")
    workflow.connect(reconAll, "pial", outputnode, "pial")
    workflow.connect(reconAll, "white", outputnode, "white")
    workflow.connect(reconAll, "subject_id", outputnode, "subject_id")
    workflow.connect(reconAll, "subjects_dir", outputnode, "subjects_dir")
    workflow.connect(aparaseg2Volmgz, "vol_label_file", outputnode, "vol_label_file")

    if is_hippo_amyg_labels:
        # NODE 10: Segmentation of the hippocampal substructures and the nuclei of the amygdala
        segmentHA = Node(SegmentHA(), name="segmentHA")
        workflow.connect(reconAll, "subjects_dir", segmentHA, "subjects_dir")
        workflow.connect(reconAll, "subject_id", segmentHA, "subject_id")
        workflow.connect(inputnode, "max_node_cpu", segmentHA, "num_threads")

        workflow.connect(segmentHA, "lh_hippoAmygLabels", outputnode, "lh_hippoAmygLabels")
        workflow.connect(segmentHA, "rh_hippoAmygLabels", outputnode, "rh_hippoAmygLabels")

    return workflow
