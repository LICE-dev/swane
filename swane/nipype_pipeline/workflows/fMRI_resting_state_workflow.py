from nipype import Node, IdentityInterface, SelectFiles, Merge
from nipype.interfaces.fsl import (
    MELODIC,
    ApplyXFM
)
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow
from swane.config.config_enums import SLICE_TIMING


def fMRI_resting_state_workflow(
    name: str, dicom_dir: str, config: SectionProxy, base_dir: str = "/"
) -> CustomWorkflow:
    """
    fMRI resting state anlysis

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The directory path of the DICOM files.
    config: SectionProxy
        workflow settings.
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    ref_brain : path
        Betted T13D.

    Output Node Fields
    ----------
    IC : path
        Independent components 4d nifti.

    Returns
    -------
    workflow : CustomWorkflow
        The fMRI workflow.

    """

    TR = config.getfloat_safe("tr")
    n_vols = config.getint_safe("n_vols")
    del_start_vols = config.getint_safe("del_start_vols")
    del_end_vols = config.getint_safe("del_end_vols")

    workflow = fMRI_preproc_workflow(name=name, dicom_dir=dicom_dir, TR=TR, slice_timing=SLICE_TIMING.UNKNOWN, n_vols=n_vols,
                                     hpcutoff=100, del_start_vols=del_start_vols, del_end_vols=del_end_vols,
                                     base_dir=base_dir)

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "IC",
            ]
        ),
        name="outputnode",
    )

    # Get nodes for further connection
    getTR = workflow.get_node("%s_getTR" % name)
    del_vols = workflow.get_node("%s_del_vols" % name)
    motion_correct = workflow.get_node("%s_motion_correct" % name)
    dilatemask = workflow.get_node("%s_dilatemask" % name)
    flirt_2_ref = workflow.get_node("%s_flirt_2_ref" % name)
    highpass = workflow.get_node("%s_highpass" % name) # this is the final preprocessing file
    inputnode = workflow.get_node("inputnode")

    input_list = Node(Merge(1), name="merge_node")
    workflow.connect(highpass, "out_file", input_list, "in1")

    melodic = Node(MELODIC(), name="melodic")
    melodic.inputs.mm_thresh = 0.5
    # TODO: valutare se creare una impostazione per limitare il numero di IC
    melodic.inputs.dim = 0
    melodic.inputs.out_stats = True
    melodic.inputs.no_bet = True
    melodic.inputs.report = True
    workflow.connect(input_list, "out", melodic, "in_files")
    workflow.connect(dilatemask, "out_file", melodic, "mask")
    workflow.connect(getTR, "TR", melodic, "tr_sec")

    templates = dict(IC="melodic_IC.nii.gz",
                     mel_mix="melodic_mix",
                     mel_ft_mix="melodic_FTmix",
                     thresh_zstat_files="stats/thresh_zstat*.nii.gz")

    melodic_output = Node(SelectFiles(templates), name="melodic_output")
    melodic_output.inputs.sorted = True
    workflow.connect(melodic, "out_dir", melodic_output, "melodic_dir")
    workflow.connect(melodic, "out_dir", melodic_output, "base_directory")

    IC_2_ref = Node(ApplyXFM(), name="IC_2_ref")
    IC_2_ref.long_name = "IC to reference space"
    IC_2_ref.inputs.out_file = "r-melodic_IC.nii.gz"
    IC_2_ref.inputs.interp = "trilinear"
    workflow.connect(melodic_output, "IC", IC_2_ref, "in_file")
    workflow.connect(flirt_2_ref, "out_matrix_file", IC_2_ref, "in_matrix_file")
    workflow.connect(inputnode, "ref_brain", IC_2_ref, "reference")

    workflow.connect(IC_2_ref, "out_file", outputnode, "IC")

    return workflow
