from nipype import Node, IdentityInterface, Merge, SelectFiles
from nipype.algorithms.modelgen import SpecifyModel
from nipype.algorithms.rapidart import ArtifactDetect
from nipype.interfaces.fsl import (ImageMaths, ExtractROI, MCFLIRT, BET, ImageStats, SUSAN, FLIRT, Level1Design,
                                   FEATModel, FILMGLS, SmoothEstimate, Cluster, ApplyXFM)
from configparser import SectionProxy
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.FslNVols import FslNVols
from swane.nipype_pipeline.nodes.FMRIGenSpec import FMRIGenSpec
from swane.nipype_pipeline.nodes.CustomSliceTimer import CustomSliceTimer
from swane.nipype_pipeline.nodes.GetNiftiTR import GetNiftiTR
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.DeleteVolumes import DeleteVolumes
from swane.config.config_enums import BLOCK_DESIGN


def task_fMRI_workflow(name: str, dicom_dir: str, config: SectionProxy, base_dir: str = "/") -> CustomWorkflow:
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
    ref_BET : path
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

    workflow = CustomWorkflow(name=name, base_dir=base_dir)
    
    # Input Node
    inputnode = Node(
        IdentityInterface(
            fields=['ref_BET']),
        name='inputnode')

    task_a_name = config["task_a_name"].replace(" ", "_")
    task_b_name = config["task_b_name"].replace(" ", "_")
    task_duration = config.getint_safe('task_duration')
    rest_duration = config.getint_safe('rest_duration')
    TR = config.getfloat_safe('tr')
    slice_timing = config.getenum_safe('slice_timing')
    n_vols = config.getint_safe('n_vols')
    del_start_vols = config.getint_safe('del_start_vols')
    del_end_vols = config.getint_safe('del_end_vols')
    block_design = config.getenum_safe('block_design')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['threshold_file_cont1_thresh1', 'threshold_file_cont1_thresh2', 'threshold_file_cont1_thresh3',
                                  'threshold_file_cont2_thresh1', 'threshold_file_cont2_thresh2', 'threshold_file_cont2_thresh3']),
        name='outputnode')

    # NODE 1: Conversion dicom -> nifti
    conversion = Node(CustomDcm2niix(), name='%s_conv' % name)
    conversion.inputs.out_filename = name
    conversion.inputs.bids_format = False
    conversion.inputs.source_dir = dicom_dir
    conversion.inputs.name_conflicts = 1
    conversion.inputs.merge_imgs = 2

    # NODE 2: Get EPI volume numbers
    nvols = Node(FslNVols(), name="%s_nvols" % name)
    nvols.long_name = "EPI volumes count"
    nvols.inputs.force_value = n_vols
    workflow.connect(conversion, 'converted_files', nvols, 'in_file')

    # NODE 3: Get Repetition Time
    getTR = Node(GetNiftiTR(), name="%s_getTR" % name)
    getTR.long_name = "get TR"
    getTR.inputs.force_value = TR
    workflow.connect(conversion, 'converted_files', getTR, 'in_file')

    # NODE 4: Delete specified volumes at start and end of sequence
    del_vols = Node(DeleteVolumes(), name="%s_del_vols" % name)
    del_vols.long_name = "Extreme volumes deletion"
    del_vols.inputs.del_start_vols = del_start_vols
    del_vols.inputs.del_end_vols = del_end_vols
    workflow.connect(conversion, 'converted_files', del_vols, "in_file")
    workflow.connect(nvols, 'nvols', del_vols, "nvols")

    # NODE 5: Orienting in radiological convention
    reorient = Node(ForceOrient(), name='%s_reorient' % name)
    workflow.connect(del_vols, "out_file", reorient, "in_file")

    # NODE 5: Convert functional images to float representation.
    img2float = Node(ImageMaths(), name="%s_img2float" % name)
    img2float.long_name = "Intensity in float values"
    img2float.inputs.out_data_type = 'float'
    img2float.inputs.op_string = ''
    img2float.inputs.suffix = '_dtype'
    workflow.connect(reorient, 'out_file', img2float, 'in_file')

    # NODE 6: Extract the middle volume of the first run as the reference
    extract_ref = Node(ExtractROI(), name="%s_extract_ref" % name)
    extract_ref.long_name = "Reference volume selection"
    extract_ref.inputs.t_size = 1

    # Function to extract the middle volume number
    def get_middle_volume(func):
        from nibabel import load
        funcfile = func
        if isinstance(func, list):
            funcfile = func[0]
        _, _, _, timepoints = load(funcfile).shape
        middle = int(timepoints / 2)
        return middle

    workflow.connect(img2float, 'out_file', extract_ref, 'in_file')
    workflow.connect(reorient, ('out_file', get_middle_volume), extract_ref, 't_min')

    # NODE 7: Realign the functional runs to the middle volume of the first run
    motion_correct = Node(MCFLIRT(), name="%s_motion_correct" % name)
    motion_correct.inputs.save_mats = True
    motion_correct.inputs.save_plots = True
    motion_correct.inputs.save_rms = True
    motion_correct.inputs.interpolation = 'spline'
    workflow.connect(img2float, 'out_file', motion_correct, 'in_file')
    workflow.connect(extract_ref, 'roi_file', motion_correct, 'ref_file')

    # NODE 8: Perform slice timing correction if needed
    slice_timing_correction = Node(CustomSliceTimer(), name="%s_timing_correction" % name)
    slice_timing_correction.inputs.slice_timing = slice_timing
    workflow.connect(getTR, 'TR', slice_timing_correction, 'time_repetition')
    workflow.connect(motion_correct, 'out_file', slice_timing_correction, 'in_file')

    # NODE 9: Extract the mean volume of the first functional run
    meanfunc = Node(ImageMaths(), name="%s_meanfunc" % name)
    meanfunc.long_name = "mean image calculation"
    meanfunc.inputs.op_string = '-Tmean'
    meanfunc.inputs.suffix = '_mean'
    workflow.connect(slice_timing_correction, 'slice_time_corrected_file', meanfunc, 'in_file')

    # NODE 10: Strip the skull from the mean functional to generate a mask
    meanfuncmask = Node(BET(), name="%s_meanfuncmask" % name)
    meanfuncmask.inputs.mask = True
    meanfuncmask.inputs.no_output = True
    meanfuncmask.inputs.frac = 0.3
    workflow.connect(meanfunc, 'out_file', meanfuncmask, 'in_file')

    # NODE 11: Mask the functional runs with the extracted mask
    maskfunc = Node(ImageMaths(), name="%s_maskfunc" % name)
    maskfunc.long_name = "mean image masking"
    maskfunc.inputs.suffix = '_bet'
    maskfunc.inputs.op_string = '-mas'
    workflow.connect(slice_timing_correction, 'slice_time_corrected_file', maskfunc, 'in_file')
    workflow.connect(meanfuncmask, 'mask_file', maskfunc, 'in_file2')

    # NODE 12: Determine the 2nd and 98th percentile intensities of each functional run
    getthresh = Node(ImageStats(), name="%s_getthresh" % name)
    getthresh.long_name = "2-98% threshold calculation"
    getthresh.inputs.op_string = '-p 2 -p 98'
    workflow.connect(maskfunc, 'out_file', getthresh, 'in_file')

    # NODE 13: Threshold the first run of the functional data at 10% of the 98th percentile
    threshold = Node(ImageMaths(), name="%s_threshold" % name)
    threshold.long_name = "thresholding"
    threshold.inputs.out_data_type = 'char'
    threshold.inputs.suffix = '_thresh'

    # NODE 14: Define a function to get 10% of the intensity
    def get_thresh_op(thresh):
        return '-thr %.10f -Tmin -bin' % (0.1 * thresh[1])

    # NODE 15: Determine the median value of the functional runs using the mask
    workflow.connect(maskfunc, 'out_file', threshold, 'in_file')
    workflow.connect(getthresh, ('out_stat', get_thresh_op), threshold, 'op_string')

    # NODE 16: Determine the median value of the functional runs using the mask
    medianval = Node(ImageStats(), name="%s_medianval" % name)
    medianval.long_name = "median value calculation"
    medianval.inputs.op_string = '-k %s -p 50'
    workflow.connect(slice_timing_correction, 'slice_time_corrected_file', medianval, 'in_file')
    workflow.connect(threshold, 'out_file', medianval, 'mask_file')

    # NODE 17: Dilate the mask
    dilatemask = Node(ImageMaths(), name="%s_dilatemask" % name)
    dilatemask.long_name = "Dilate the mask"
    dilatemask.inputs.suffix = '_dil'
    dilatemask.inputs.op_string = '-dilF'
    workflow.connect(threshold, 'out_file', dilatemask, 'in_file')

    # NODE 18: Mask the motion corrected functional runs with the dilated mask
    maskfunc2 = Node(ImageMaths(), name="%s_maskfunc2" % name)
    maskfunc2.long_name = "corrected images masking"
    maskfunc2.inputs.suffix = '_mask'
    maskfunc2.inputs.op_string = '-mas'
    workflow.connect(slice_timing_correction, 'slice_time_corrected_file', maskfunc2, 'in_file')
    workflow.connect(dilatemask, 'out_file', maskfunc2, 'in_file2')

    # NODE 19: Determine the mean image from each functional run
    meanfunc2 = Node(ImageMaths(), name="%s_meanfunc2" % name)
    meanfunc2.long_name = "Mean image calculation"
    meanfunc2.inputs.op_string = '-Tmean'
    meanfunc2.inputs.suffix = '_mean'
    workflow.connect(maskfunc2, 'out_file', meanfunc2, 'in_file')

    # NODE 20: Merge the median values with the mean functional images into a coupled list
    mergenode = Node(Merge(2), name="%s_mergenode" % name)
    mergenode.long_name = "Mean and median coupling"
    workflow.connect(meanfunc2, 'out_file', mergenode, 'in1')
    workflow.connect(medianval, 'out_stat', mergenode, 'in2')

    # NODE 21: Smooth each run using SUSAN with the brightness threshold set to 75% of the
    # median value for each run and a mask constituting the mean functional
    smooth = Node(SUSAN(), name="%s_smooth" % name)
    # Nipype uses a different algorithm to calculate it ->
    # float(fwhm) / np.sqrt(8 * np.log(2)).
    # Therefore, to get 2.12314225053, fwhm should be 4.9996179300001655 instead of 5
    fwhm_thr = 4.9996179300001655
    smooth.inputs.fwhm = fwhm_thr

    # Function to calculate the 75% of the median value
    def get_bt_thresh(medianvals):
        return 0.75 * medianvals
    
    # Function to define the couple of values
    def get_usans(x):
        return [tuple([x[0], 0.75 * x[1]])]

    workflow.connect(maskfunc2, 'out_file', smooth, 'in_file')
    workflow.connect(medianval, ('out_stat', get_bt_thresh), smooth, 'brightness_threshold')
    workflow.connect(mergenode, ('out', get_usans), smooth, 'usans')

    # NODE 22: Mask the smoothed data with the dilated mask
    maskfunc3 = Node(ImageMaths(), name="%s_maskfunc3" % name)
    maskfunc3.long_name = "denoised images masking"
    maskfunc3.inputs.suffix = '_mask'
    maskfunc3.inputs.op_string = '-mas'
    workflow.connect(smooth, 'smoothed_file', maskfunc3, 'in_file')
    workflow.connect(dilatemask, 'out_file', maskfunc3, 'in_file2')

    # NODE 23: Scale each volume of the run so that the median value of the run is set to 10000
    intnorm = Node(ImageMaths(), name="%s_intnorm" % name)
    intnorm.long_name = "intensity normalization"
    intnorm.inputs.suffix = '_intnorm'

    # Function to get the scaling factor operation string for intensity normalization
    def get_inorm_scale(medianvals):
        return '-mul %.10f' % (10000. / medianvals)

    workflow.connect(maskfunc3, 'out_file', intnorm, 'in_file')
    workflow.connect(medianval, ('out_stat', get_inorm_scale), intnorm, 'op_string')

    # NODE 24: Generate a mean functional image from the first run
    meanfunc3 = Node(ImageMaths(), name="%s_meanfunc3" % name)
    meanfunc3.long_name = "mean image calculation"
    meanfunc3.inputs.op_string = '-Tmean'
    meanfunc3.inputs.suffix = '_mean'
    workflow.connect(intnorm, 'out_file', meanfunc3, 'in_file')

    # NODE 25: Generate the Bunch containing fMRI specifications
    genSpec = Node(FMRIGenSpec(), name="%s_genSpec" % name)
    genSpec.inputs.block_design = block_design
    genSpec.inputs.task_duration = task_duration
    genSpec.inputs.rest_duration = rest_duration
    genSpec.inputs.task_a_name = task_a_name
    genSpec.inputs.task_b_name = task_b_name
    workflow.connect(getTR, "TR", genSpec, "TR")
    workflow.connect(del_vols, "nvols", genSpec, "nvols")
    workflow.connect(meanfunc3, "out_file", genSpec, "tempMean")

    # NODE 26: Perform temporal highpass filtering on the data
    highpass = Node(ImageMaths(), name="%s_highpass" % name)
    highpass.long_name = "Highpass temporal filtering"
    highpass.inputs.suffix = '_tempfilt'
    highpass.inputs.suffix = '_hpf'
    workflow.connect(genSpec, 'hpstring', highpass, 'op_string')
    workflow.connect(intnorm, 'out_file', highpass, 'in_file')

    # NODE 27: Coregister the mean functional image to the structural image
    flirt_2_ref = Node(FLIRT(), name="%s_flirt_2_ref" % name)
    flirt_2_ref.long_name = "%s to reference space"
    flirt_2_ref.inputs.out_matrix_file = "fMRI2ref.mat"
    flirt_2_ref.inputs.cost = "corratio"
    flirt_2_ref.inputs.searchr_x = [-90, 90]
    flirt_2_ref.inputs.searchr_y = [-90, 90]
    flirt_2_ref.inputs.searchr_z = [-90, 90]
    flirt_2_ref.inputs.dof = 6
    workflow.connect(meanfunc2, 'out_file', flirt_2_ref, 'in_file')
    workflow.connect(inputnode, 'ref_BET', flirt_2_ref, 'reference')

    # NODE 28: Determine which of the images in the functional series are outliers
    # based on deviations in intensity and/or movement.
    art = Node(ArtifactDetect(), name="%s_art" % name)
    art.inputs.use_differences = [True, False]
    art.inputs.use_norm = True
    art.inputs.norm_threshold = 1
    art.inputs.zintensity_threshold = 3
    art.inputs.parameter_source = 'FSL'
    art.inputs.mask_type = 'file'
    workflow.connect(motion_correct, 'par_file', art, 'realignment_parameters')
    workflow.connect(motion_correct, 'out_file', art, 'realigned_files')
    workflow.connect(dilatemask, 'out_file', art, 'mask_file')

    # NODE 29: Generate design information.
    modelspec = Node(SpecifyModel(), name="%s_modelspec" % name)
    modelspec.inputs.input_units = 'secs'
    workflow.connect(genSpec, 'hpcutoff', modelspec, 'high_pass_filter_cutoff')
    workflow.connect(genSpec, 'evs_run', modelspec, 'subject_info')
    workflow.connect(getTR, 'TR', modelspec, 'time_repetition')
    workflow.connect(highpass, 'out_file', modelspec, 'functional_runs')
    workflow.connect(art, 'outlier_files', modelspec, 'outlier_files')
    workflow.connect(motion_correct, 'par_file', modelspec, 'realignment_parameters')

    # NODE 30: Generate a run specific fsf file for analysis
    level_1_design = Node(Level1Design(), name="%s_level_1_design" % name)
    level_1_design.inputs.bases = {'dgamma': {'derivs': False}}
    level_1_design.inputs.model_serial_correlations = True
    workflow.connect(genSpec, 'contrasts', level_1_design, 'contrasts')
    workflow.connect(getTR, 'TR', level_1_design, 'interscan_interval')
    workflow.connect(modelspec, 'session_info', level_1_design, 'session_info')

    # NODE 31: Generate a run specific mat file for use by FILMGLS
    modelgen = Node(FEATModel(), name="%s_modelgen" % name)
    workflow.connect(level_1_design, 'fsf_files', modelgen, 'fsf_file')
    workflow.connect(level_1_design, 'ev_files', modelgen, 'ev_files')

    # NODE 32: estimate a model specified by a mat file and a functional run
    modelestimate = Node(FILMGLS(), name="%s_modelestimate" % name)
    modelestimate.inputs.smooth_autocorr = True
    modelestimate.inputs.mask_size = 5
    modelestimate.inputs.threshold = 1000
    workflow.connect(highpass, 'out_file', modelestimate, 'in_file')
    workflow.connect(modelgen, 'design_file', modelestimate, 'design_file')
    workflow.connect(modelgen, 'con_file', modelestimate, 'tcon_file')

    # NODE 33: Get smoothness parameters
    smoothness = Node(SmoothEstimate(), name='%s_smoothness' % name)
    workflow.connect(modelestimate, 'residual4d', smoothness, 'residual_fit_file')

    # Function to read degree of freedom file
    def dof_from_file(dofFile):
        # Function used out of the box. Import needed
        import os  # TODO trovare modo per sopprimere alert
        if os.path.exists(dofFile):
            with open(dofFile, 'r') as file:
                for line in file.readlines():
                    return int(line)

    workflow.connect(modelestimate, ('dof_file', dof_from_file), smoothness, 'dof')
    workflow.connect(dilatemask, 'out_file', smoothness, 'mask_file')

    n_contrasts = 1
    if block_design == BLOCK_DESIGN.RARB:
        n_contrasts += 1
    cont = 0
    while cont < n_contrasts:
        cont += 1

        # NODE 34: Select all result file from filmgls output folder
        results_select = Node(SelectFiles({'cope': 'cope%d.nii.gz' % cont, 'zstat': 'zstat%d.nii.gz' % cont}),
                              name="%s_results_select_%d" % (name, cont))
        results_select.long_name = "contrast %d result selection" % cont
        workflow.connect(modelestimate, 'results_dir', results_select, 'base_directory')

        # NODE 35: Mask z-stat with the dilated mask
        maskfunc4 = Node(ImageMaths(), name="%s_maskfunc4_%d" % (name, cont))
        maskfunc4.long_name = "Zstat masking"
        maskfunc4.inputs.suffix = '_mask'
        maskfunc4.inputs.op_string = '-mas'
        workflow.connect(results_select, 'zstat', maskfunc4, 'in_file')
        workflow.connect(dilatemask, 'out_file', maskfunc4, 'in_file2')

        # Function to generate the name for the file of output cluster
        def cluster_file_name(contrasts, thres, run_name, x):
            return "r-%s_cluster_%s_threshold%.1f.nii.gz" % (run_name, contrasts[x-1][0], thres)
        
        # NODE 36a: Perform clustering on statistical output
        threshold = 3.1
        cluster1 = Node(Cluster(), name="%s_cluster_t3_%d" % (name, cont))
        cluster1.long_name = "contrast " + str(cont) + " threshold " + str(threshold) + " %s in reference space"
        cluster1.inputs.threshold = threshold
        cluster1.inputs.connectivity = 26
        cluster1.inputs.pthreshold = 0.05
        cluster1.inputs.out_localmax_txt_file = True
        
        workflow.connect([(genSpec, cluster1, [(('contrasts', cluster_file_name, threshold, name, cont), 'out_threshold_file')])])
        workflow.connect(maskfunc4, 'out_file', cluster1, 'in_file')
        workflow.connect(results_select, 'cope', cluster1, 'cope_file')
        workflow.connect(smoothness, 'volume', cluster1, 'volume')
        workflow.connect(smoothness, 'dlh', cluster1, 'dlh')

        # NODE 37a: Transformation in ref space
        cluster1_2_ref = Node(ApplyXFM(), name="%s_cluster_t3_%d_to_ref" % (name, cont))
        cluster1_2_ref.long_name = "contrast " + str(cont) + " threshold " + str(threshold) + " %s in reference space"
        cluster1_2_ref.inputs.apply_xfm = True
        workflow.connect(cluster1, 'threshold_file', cluster1_2_ref, 'in_file')
        workflow.connect([(genSpec, cluster1_2_ref, [(('contrasts', cluster_file_name, threshold, name, cont), 'out_file')])])
        workflow.connect(inputnode, "ref_BET", cluster1_2_ref, "reference")
        workflow.connect(flirt_2_ref, "out_matrix_file", cluster1_2_ref, "in_matrix_file")

        workflow.connect(cluster1_2_ref, 'out_file', outputnode, 'threshold_file_cont%s_thresh1' % cont)
        
        # NODE 36b: Perform clustering on statistical output
        threshold = 5
        cluster2 = Node(Cluster(), name="%s_cluster_t5_%d" % (name, cont))
        cluster2.long_name = "contrast " + str(cont) + " threshold " + str(threshold) + " %s in reference space"
        cluster2.inputs.threshold = threshold
        cluster2.inputs.connectivity = 26
        cluster2.inputs.pthreshold = 0.05
        cluster2.inputs.out_localmax_txt_file = True
        
        workflow.connect([(genSpec, cluster2, [(('contrasts', cluster_file_name, threshold, name, cont), 'out_threshold_file')])])
        workflow.connect(maskfunc4, 'out_file', cluster2, 'in_file')
        workflow.connect(results_select, 'cope', cluster2, 'cope_file')
        workflow.connect(smoothness, 'volume', cluster2, 'volume')
        workflow.connect(smoothness, 'dlh', cluster2, 'dlh')

        # NODE 37b: Transformation in ref space
        cluster2_2_ref = Node(ApplyXFM(), name="%s_cluster_t5_%d_to_ref" % (name, cont))
        cluster2_2_ref.long_name = "contrast " + str(cont) + " threshold " + str(threshold) + " %s in reference space"
        cluster2_2_ref.inputs.apply_xfm = True
        workflow.connect(cluster2, 'threshold_file', cluster2_2_ref, 'in_file')
        workflow.connect([(genSpec, cluster2_2_ref, [(('contrasts', cluster_file_name, threshold, name, cont), 'out_file')])])
        workflow.connect(inputnode, "ref_BET", cluster2_2_ref, "reference")
        workflow.connect(flirt_2_ref, "out_matrix_file", cluster2_2_ref, "in_matrix_file")

        workflow.connect(cluster2_2_ref, 'out_file', outputnode, 'threshold_file_cont%s_thresh2' % cont)
        
        # NODE 36c: Perform clustering on statistical output
        threshold = 7
        cluster3 = Node(Cluster(), name="%s_cluster_t7_%d" % (name, cont))
        cluster3.long_name = "contrast " + str(cont) + " threshold " + str(threshold) + " %s in reference space"
        cluster3.inputs.threshold = threshold
        cluster3.inputs.connectivity = 26
        cluster3.inputs.pthreshold = 0.05
        cluster3.inputs.out_localmax_txt_file = True
        
        workflow.connect([(genSpec, cluster3, [(('contrasts', cluster_file_name, threshold, name, cont), 'out_threshold_file')])])
        workflow.connect(maskfunc4, 'out_file', cluster3, 'in_file')
        workflow.connect(results_select, 'cope', cluster3, 'cope_file')
        workflow.connect(smoothness, 'volume', cluster3, 'volume')
        workflow.connect(smoothness, 'dlh', cluster3, 'dlh')

        # NODE 37c: Transformation in ref space
        cluster3_2_ref = Node(ApplyXFM(), name="%s_cluster_t7_%d_to_ref" % (name, cont))
        cluster3_2_ref.long_name = "contrast " + str(cont) + " threshold " + str(threshold) + " %s in reference space"
        cluster3_2_ref.inputs.apply_xfm = True
        workflow.connect(cluster3, 'threshold_file', cluster3_2_ref, 'in_file')
        workflow.connect([(genSpec, cluster3_2_ref, [(('contrasts', cluster_file_name, threshold, name, cont), 'out_file')])])
        workflow.connect(inputnode, "ref_BET", cluster3_2_ref, "reference")
        workflow.connect(flirt_2_ref, "out_matrix_file", cluster3_2_ref, "in_matrix_file")

        workflow.connect(cluster3_2_ref, 'out_file', outputnode, 'threshold_file_cont%s_thresh3' % cont)

    return workflow
