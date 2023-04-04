from nipype import Node, IdentityInterface, Merge, SelectFiles
from nipype.algorithms.modelgen import SpecifyModel
from nipype.algorithms.rapidart import ArtifactDetect
from nipype.interfaces.fsl import ImageMaths, ExtractROI, MCFLIRT, BET, ImageStats, SUSAN, FLIRT, Level1Design, \
    FEATModel, FILMGLS, SmoothEstimate

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.nodes.CustomDcm2niix import CustomDcm2niix
from swane.nipype_pipeline.nodes.FslNVols import FslNVols
from swane.nipype_pipeline.nodes.FslCluster import FslCluster
from swane.nipype_pipeline.nodes.FMRIGenSpec import FMRIGenSpec
from swane.nipype_pipeline.nodes.CustomSliceTimer import CustomSliceTimer
from swane.nipype_pipeline.nodes.GetNiftiTR import GetNiftiTR
from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient
from swane.nipype_pipeline.nodes.DeleteVolumes import DeleteVolumes


def task_fMRI_workflow(name: str, dicom_dir: str, design_block: int, base_dir: str = "/") -> CustomWorkflow:
    """
    fMRI first level anlysis for a single task with constant task-rest paradigm.

    Parameters
    ----------
    name : str
        The workflow name.
    dicom_dir : path
        The directory path of the DICOM files.
    design_block : int
        Task design block:
            0: rArA...
            1: rArBrArB...
    base_dir : path, optional
        The base directory path relative to parent workflow. The default is "/".

    Input Node Fields
    ----------
    task_a_name : str
        The name of the task A.
    task_b_name : str
        The name of the task B.
    nvols : int
        If == -1, automatic detection of EPI volume number, otherwise force to specified number.
    TR : float
        If == -1, automatic detection of Repetition Time, otherwise force to specified number.
    slice_timing : int
        Slice order for timing correction:
            0, Unknown, correction disabled
            1, Regular up
            2, Regular down
            3, intervealed
    task_duration : int
        Duration of task in seconds.
    ref_BET : path
        Betted T13D.
    rest_duration : int
        Duration of rest in second.
    del_start_vols : int
        Volumes to delete from start of sequence.
    del_end_vols : int
        Volumes to delete from end of sequence.

    Returns
    -------
    workflow : CustomWorkflow
        The fMRI workflow.
        
    Output Node Fields
    ----------
    threshold_file_1 : path
        Cluster of activation (task A vs rest or Task A vs Task B) in T13D reference space.
    threshold_file_2 : path
        Cluster of activation (task b vs Task) in T13D reference space.

    """
    
    #TODO rinominare in workflow
    workflow = CustomWorkflow(name=name, base_dir=base_dir)
    
    # Input Node
    inputnode = Node(
        IdentityInterface(
            fields=['task_a_name', 'task_b_name', 'nvols', 'TR', 'slice_timing', 'task_duration', 'ref_BET',
                    'rest_duration', 'del_start_vols', 'del_end_vols']),
        name='inputnode')
    
    # Output Node
    outputnode = Node(
        IdentityInterface(fields=['threshold_file_1', 'threshold_file_2']),
        name='outputnode')

    # NODE 1: Conversion dicom -> nifti
    conv = Node(CustomDcm2niix(), name='%s_conv' % name)
    conv.inputs.out_filename = name
    conv.inputs.bids_format = False
    conv.inputs.source_dir = dicom_dir

    # NODE 2: Get EPI volume numbers
    nvols = Node(FslNVols(), name="%s_nvols" % name)
    nvols.long_name = "EPI volumes count"
    workflow.connect(inputnode, 'nvols', nvols, 'force_value')
    workflow.connect(conv, 'converted_files', nvols, 'in_file')

    # NODE 3: Get Repetition Time
    getTR = Node(GetNiftiTR(), name="%s_getTR" % name)
    getTR.long_name = "get TR"
    workflow.connect(inputnode, 'TR', getTR, 'force_value')
    workflow.connect(conv, 'converted_files', getTR, 'in_file')

    # NODE 4: Delete specified volumes at start and end of sequence
    del_vols = Node(DeleteVolumes(), name="%s_del_vols" % name)
    del_vols.long_name = "Extreme volumes deletion"
    workflow.connect(conv, 'converted_files', del_vols, "in_file")
    workflow.connect(nvols, 'nvols', del_vols, "nvols")
    workflow.connect(inputnode, 'del_start_vols', del_vols, "del_start_vols")
    workflow.connect(inputnode, 'del_end_vols', del_vols, "del_end_vols")

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
    workflow.connect(getTR, 'TR', slice_timing_correction, 'time_repetition')
    workflow.connect(motion_correct, 'out_file', slice_timing_correction, 'in_file')
    workflow.connect(inputnode, 'slice_timing', slice_timing_correction, 'slice_timing')

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
    genSpec.inputs.design_block = design_block
    workflow.connect(inputnode, 'task_duration', genSpec, 'task_duration')
    workflow.connect(inputnode, 'rest_duration', genSpec, 'rest_duration')
    workflow.connect(inputnode, 'task_a_name', genSpec, 'task_a_name')
    workflow.connect(inputnode, 'task_b_name', genSpec, 'task_b_name')
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

    n_contrasts = 1 + design_block
    cont = 0
    while cont < n_contrasts:
        cont += 1

        # NODE 34: Select all result file from filmgls output folder
        results_select = Node(SelectFiles({'cope': 'cope%d.nii.gz' % cont,
                                                'zstat': 'zstat%d.nii.gz' % cont}),
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

        # NODE 36: Perform clustering on statistical output
        cluster = Node(FslCluster(), name="%s_cluster_%d" % (name, cont))
        cluster.long_name = "contrast " + str(cont) + " %"
        cluster.inputs.threshold = 3.1
        cluster.inputs.connectivity = 26
        cluster.inputs.pthreshold = 0.05
        cluster.inputs.out_localmax_txt_file = True

        # Function to generate the name for the file of output cluster
        def cluster_file_name(contrasts, run_name, x):
            return "r-%s_cluster_%s.nii.gz" % (run_name, contrasts[x-1][0])

        workflow.connect([(genSpec, cluster, [(('contrasts', cluster_file_name, name, cont), 'out_threshold_file')])])
        workflow.connect(maskfunc4, 'out_file', cluster, 'in_file')
        workflow.connect(results_select, 'cope', cluster, 'cope_file')
        workflow.connect(smoothness, 'volume', cluster, 'volume')
        workflow.connect(smoothness, 'dlh', cluster, 'dlh')
        workflow.connect(inputnode, "ref_BET", cluster, "std_space_file")
        workflow.connect(flirt_2_ref, "out_matrix_file", cluster, "xfm_file")

        workflow.connect(cluster, 'threshold_file', outputnode, 'threshold_file_%s' % cont)

    return workflow
