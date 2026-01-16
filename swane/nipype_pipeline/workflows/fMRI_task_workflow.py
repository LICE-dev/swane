from nipype import Node, IdentityInterface, SelectFiles
from nipype.algorithms.modelgen import SpecifyModel
from nipype.algorithms.rapidart import ArtifactDetect
from nipype.interfaces.fsl import (
    ImageMaths,
    Level1Design,
    FEATModel,
    FILMGLS,
    SmoothEstimate,
    Cluster,
    ApplyXFM,
)
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.FMRIGenSpec import FMRIGenSpec
from swane.config.config_enums import BLOCK_DESIGN
from swane.nipype_pipeline.workflows.fMRI_preproc_workflow import fMRI_preproc_workflow


def fMRI_task_workflow(
    name: str, dicom_dir: str, config: SectionProxy, base_dir: str = "/"
) -> CustomWorkflow:
    """
    fMRI first level anlysis for a single task with constant task-rest paradigm.

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
    reference_brain : path
        Betted T13D.

    Output Node Fields
    ----------
    threshold_file_1 : path
        Cluster of activation (task A vs rest or Task A vs Task B) in T13D reference space.
    threshold_file_2 : path
        Cluster of activation (task b vs Task) in T13D reference space.

    Returns
    -------
    workflow : CustomWorkflow
        The fMRI workflow.

    """

    task_a_name = config["task_a_name"].replace(" ", "_")
    task_b_name = config["task_b_name"].replace(" ", "_")
    task_duration = config.getint_safe("task_duration")
    rest_duration = config.getint_safe("rest_duration")
    TR = config.getfloat_safe("tr")
    slice_timing = config.getenum_safe("slice_timing")
    n_vols = config.getint_safe("n_vols")
    del_start_vols = config.getint_safe("del_start_vols")
    del_end_vols = config.getint_safe("del_end_vols")
    block_design = config.getenum_safe("block_design")
    hpcutoff = task_duration + rest_duration
    if block_design == BLOCK_DESIGN.RARB:
        hpcutoff = hpcutoff * 2

    workflow = fMRI_preproc_workflow(
        name=name,
        dicom_dir=dicom_dir,
        TR=TR,
        slice_timing=slice_timing,
        n_vols=n_vols,
        hpcutoff=hpcutoff,
        del_start_vols=del_start_vols,
        del_end_vols=del_end_vols,
        base_dir=base_dir,
    )

    # Output Node
    outputnode = Node(
        IdentityInterface(
            fields=[
                "threshold_file_cont1_thresh1",
                "threshold_file_cont1_thresh2",
                "threshold_file_cont1_thresh3",
                "threshold_file_cont2_thresh1",
                "threshold_file_cont2_thresh2",
                "threshold_file_cont2_thresh3",
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
    highpass = workflow.get_node("%s_highpass" % name)
    inputnode = workflow.get_node("inputnode")

    # NODE 25: Generate the Bunch containing fMRI specifications
    genSpec = Node(FMRIGenSpec(), name="%s_genSpec" % name)
    genSpec.inputs.block_design = block_design
    genSpec.inputs.task_duration = task_duration
    genSpec.inputs.rest_duration = rest_duration
    genSpec.inputs.task_a_name = task_a_name
    genSpec.inputs.task_b_name = task_b_name
    workflow.connect(getTR, "TR", genSpec, "TR")
    workflow.connect(del_vols, "nvols", genSpec, "nvols")

    # NODE 28: Determine which of the images in the functional series are outliers
    # based on deviations in intensity and/or movement.
    art = Node(ArtifactDetect(), name="%s_art" % name)
    art.inputs.use_differences = [True, False]
    art.inputs.use_norm = True
    art.inputs.norm_threshold = 1
    art.inputs.zintensity_threshold = 3
    art.inputs.parameter_source = "FSL"
    art.inputs.mask_type = "file"
    workflow.connect(motion_correct, "par_file", art, "realignment_parameters")
    workflow.connect(motion_correct, "out_file", art, "realigned_files")
    workflow.connect(dilatemask, "out_file", art, "mask_file")

    # NODE 29: Generate design information.
    modelspec = Node(SpecifyModel(), name="%s_modelspec" % name)
    modelspec.inputs.input_units = "secs"
    modelspec.inputs.high_pass_filter_cutoff = hpcutoff
    workflow.connect(genSpec, "evs_run", modelspec, "subject_info")
    workflow.connect(getTR, "TR", modelspec, "time_repetition")
    workflow.connect(highpass, "out_file", modelspec, "functional_runs")
    workflow.connect(art, "outlier_files", modelspec, "outlier_files")
    workflow.connect(motion_correct, "par_file", modelspec, "realignment_parameters")

    # NODE 30: Generate a run specific fsf file for analysis
    level_1_design = Node(Level1Design(), name="%s_level_1_design" % name)
    level_1_design.inputs.bases = {"dgamma": {"derivs": False}}
    level_1_design.inputs.model_serial_correlations = True
    workflow.connect(genSpec, "contrasts", level_1_design, "contrasts")
    workflow.connect(getTR, "TR", level_1_design, "interscan_interval")
    workflow.connect(modelspec, "session_info", level_1_design, "session_info")

    # NODE 31: Generate a run specific mat file for use by FILMGLS
    modelgen = Node(FEATModel(), name="%s_modelgen" % name)
    workflow.connect(level_1_design, "fsf_files", modelgen, "fsf_file")
    workflow.connect(level_1_design, "ev_files", modelgen, "ev_files")

    # NODE 32: estimate a model specified by a mat file and a functional run
    modelestimate = Node(FILMGLS(), name="%s_modelestimate" % name)
    modelestimate.inputs.smooth_autocorr = True
    modelestimate.inputs.mask_size = 5
    modelestimate.inputs.threshold = 1000
    workflow.connect(highpass, "out_file", modelestimate, "in_file")
    workflow.connect(modelgen, "design_file", modelestimate, "design_file")
    workflow.connect(modelgen, "con_file", modelestimate, "tcon_file")

    # NODE 33: Get smoothness parameters
    smoothness = Node(SmoothEstimate(), name="%s_smoothness" % name)
    workflow.connect(modelestimate, "residual4d", smoothness, "residual_fit_file")

    # Function to read degree of freedom file
    def dof_from_file(dofFile):
        # Function used out of the box. Import needed
        import os  # TODO trovare modo per sopprimere alert

        if os.path.exists(dofFile):
            with open(dofFile, "r") as file:
                for line in file.readlines():
                    return int(line)

    workflow.connect(modelestimate, ("dof_file", dof_from_file), smoothness, "dof")
    workflow.connect(dilatemask, "out_file", smoothness, "mask_file")

    n_contrasts = 1
    if block_design == BLOCK_DESIGN.RARB:
        n_contrasts += 1
    cont = 0
    while cont < n_contrasts:
        cont += 1

        # NODE 34: Select all result file from filmgls output folder
        results_select = Node(
            SelectFiles(
                {"cope": "cope%d.nii.gz" % cont, "zstat": "zstat%d.nii.gz" % cont}
            ),
            name="%s_results_select_%d" % (name, cont),
        )
        results_select.long_name = "contrast %d result selection" % cont
        workflow.connect(modelestimate, "results_dir", results_select, "base_directory")

        # NODE 35: Mask z-stat with the dilated mask
        maskfunc4 = Node(ImageMaths(), name="%s_maskfunc4_%d" % (name, cont))
        maskfunc4.long_name = "Zstat masking"
        maskfunc4.inputs.suffix = "_mask"
        maskfunc4.inputs.op_string = "-mas"
        workflow.connect(results_select, "zstat", maskfunc4, "in_file")
        workflow.connect(dilatemask, "out_file", maskfunc4, "in_file2")

        # Function to generate the name for the file of output cluster
        def cluster_file_name(contrasts, thres, run_name, x):
            return "r-%s_cluster_%s_threshold%.1f.nii.gz" % (
                run_name,
                contrasts[x - 1][0],
                thres,
            )

        # NODE 36a: Perform clustering on statistical output
        threshold = 3.1
        cluster1 = Node(Cluster(), name="%s_cluster_t3_%d" % (name, cont))
        cluster1.long_name = (
            "contrast "
            + str(cont)
            + " threshold "
            + str(threshold)
            + " %s in reference space"
        )
        cluster1.inputs.threshold = threshold
        cluster1.inputs.connectivity = 26
        cluster1.inputs.pthreshold = 0.05
        cluster1.inputs.out_localmax_txt_file = True

        workflow.connect(
            [
                (
                    genSpec,
                    cluster1,
                    [
                        (
                            ("contrasts", cluster_file_name, threshold, name, cont),
                            "out_threshold_file",
                        )
                    ],
                )
            ]
        )
        workflow.connect(maskfunc4, "out_file", cluster1, "in_file")
        workflow.connect(results_select, "cope", cluster1, "cope_file")
        workflow.connect(smoothness, "volume", cluster1, "volume")
        workflow.connect(smoothness, "dlh", cluster1, "dlh")

        # NODE 37a: Transformation in ref space
        cluster1_2_ref = Node(ApplyXFM(), name="%s_cluster_t3_%d_to_ref" % (name, cont))
        cluster1_2_ref.long_name = (
            "contrast "
            + str(cont)
            + " threshold "
            + str(threshold)
            + " %s in reference space"
        )
        cluster1_2_ref.inputs.apply_xfm = True
        workflow.connect(cluster1, "threshold_file", cluster1_2_ref, "in_file")
        workflow.connect(
            [
                (
                    genSpec,
                    cluster1_2_ref,
                    [
                        (
                            ("contrasts", cluster_file_name, threshold, name, cont),
                            "out_file",
                        )
                    ],
                )
            ]
        )
        workflow.connect(inputnode, "reference_brain", cluster1_2_ref, "reference")
        workflow.connect(
            flirt_2_ref, "out_matrix_file", cluster1_2_ref, "in_matrix_file"
        )

        workflow.connect(
            cluster1_2_ref,
            "out_file",
            outputnode,
            "threshold_file_cont%s_thresh1" % cont,
        )

        # NODE 36b: Perform clustering on statistical output
        threshold = 5
        cluster2 = Node(Cluster(), name="%s_cluster_t5_%d" % (name, cont))
        cluster2.long_name = (
            "contrast "
            + str(cont)
            + " threshold "
            + str(threshold)
            + " %s in reference space"
        )
        cluster2.inputs.threshold = threshold
        cluster2.inputs.connectivity = 26
        cluster2.inputs.pthreshold = 0.05
        cluster2.inputs.out_localmax_txt_file = True

        workflow.connect(
            [
                (
                    genSpec,
                    cluster2,
                    [
                        (
                            ("contrasts", cluster_file_name, threshold, name, cont),
                            "out_threshold_file",
                        )
                    ],
                )
            ]
        )
        workflow.connect(maskfunc4, "out_file", cluster2, "in_file")
        workflow.connect(results_select, "cope", cluster2, "cope_file")
        workflow.connect(smoothness, "volume", cluster2, "volume")
        workflow.connect(smoothness, "dlh", cluster2, "dlh")

        # NODE 37b: Transformation in ref space
        cluster2_2_ref = Node(ApplyXFM(), name="%s_cluster_t5_%d_to_ref" % (name, cont))
        cluster2_2_ref.long_name = (
            "contrast "
            + str(cont)
            + " threshold "
            + str(threshold)
            + " %s in reference space"
        )
        cluster2_2_ref.inputs.apply_xfm = True
        workflow.connect(cluster2, "threshold_file", cluster2_2_ref, "in_file")
        workflow.connect(
            [
                (
                    genSpec,
                    cluster2_2_ref,
                    [
                        (
                            ("contrasts", cluster_file_name, threshold, name, cont),
                            "out_file",
                        )
                    ],
                )
            ]
        )
        workflow.connect(inputnode, "reference_brain", cluster2_2_ref, "reference")
        workflow.connect(
            flirt_2_ref, "out_matrix_file", cluster2_2_ref, "in_matrix_file"
        )

        workflow.connect(
            cluster2_2_ref,
            "out_file",
            outputnode,
            "threshold_file_cont%s_thresh2" % cont,
        )

        # NODE 36c: Perform clustering on statistical output
        threshold = 7
        cluster3 = Node(Cluster(), name="%s_cluster_t7_%d" % (name, cont))
        cluster3.long_name = (
            "contrast "
            + str(cont)
            + " threshold "
            + str(threshold)
            + " %s in reference space"
        )
        cluster3.inputs.threshold = threshold
        cluster3.inputs.connectivity = 26
        cluster3.inputs.pthreshold = 0.05
        cluster3.inputs.out_localmax_txt_file = True

        workflow.connect(
            [
                (
                    genSpec,
                    cluster3,
                    [
                        (
                            ("contrasts", cluster_file_name, threshold, name, cont),
                            "out_threshold_file",
                        )
                    ],
                )
            ]
        )
        workflow.connect(maskfunc4, "out_file", cluster3, "in_file")
        workflow.connect(results_select, "cope", cluster3, "cope_file")
        workflow.connect(smoothness, "volume", cluster3, "volume")
        workflow.connect(smoothness, "dlh", cluster3, "dlh")

        # NODE 37c: Transformation in ref space
        cluster3_2_ref = Node(ApplyXFM(), name="%s_cluster_t7_%d_to_ref" % (name, cont))
        cluster3_2_ref.long_name = (
            "contrast "
            + str(cont)
            + " threshold "
            + str(threshold)
            + " %s in reference space"
        )
        cluster3_2_ref.inputs.apply_xfm = True
        workflow.connect(cluster3, "threshold_file", cluster3_2_ref, "in_file")
        workflow.connect(
            [
                (
                    genSpec,
                    cluster3_2_ref,
                    [
                        (
                            ("contrasts", cluster_file_name, threshold, name, cont),
                            "out_file",
                        )
                    ],
                )
            ]
        )
        workflow.connect(inputnode, "reference_brain", cluster3_2_ref, "reference")
        workflow.connect(
            flirt_2_ref, "out_matrix_file", cluster3_2_ref, "in_matrix_file"
        )

        workflow.connect(
            cluster3_2_ref,
            "out_file",
            outputnode,
            "threshold_file_cont%s_thresh3" % cont,
        )

    return workflow
