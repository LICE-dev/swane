APPNAME = "SWANe"
app_acronym = "Standardized Workflow for Advanced Neuroimaging in Epilepsy"
EXECBUTTONTEXT = "Execute " + APPNAME + " Workflow"
EXECBUTTONTEXT_STOP = "Stop " + APPNAME + " Workflow"
GENBUTTONTEXT = "Generate " + APPNAME + " Workflow"
PTCONFIGBUTTONTEXT = "Workflow preferences"

mainwindow_chose_working_dir = "Choose the main working directory before start to use this application"
mainwindow_chose_working_dir_title = 'Select the main working directory'
mainwindow_select_pt_folder = 'Select a patient folder'
mainwindow_ptfolder_outside_workingdir_error = "The selected folder is not in " + APPNAME + " main working directory!"
mainwindow_pt_already_loaded_error = "The selected patient was already loaded in " + APPNAME + "!"
mainwindow_invalid_folder_error = "The selected folder does not contains valid patient data!"
mainwindow_force_dir_update = "If you are SURE you selected a patient folder, " + APPNAME + "can try to update " \
                              "it.\nDo you want to update selected patient folder?"
mainwindow_max_pt_error = "Max patient tab limit reached!"
mainwindow_new_pt_name = 'Write the name of the new patient:'
mainwindow_new_pt_title = 'New patient'
mainwindow_new_pt_created = "New patient created in: "
mainwindow_new_pt_name_error = "Invalid name: "
mainwindow_pt_exists_error = "This patient already exists: "
mainwindow_shortcut_created = "Shortcut created!"
mainwindow_shortcut_removed = "Shortcut removed!"
mainwindow_home_tab_name = "Home"
mainwindow_wf_executing_error_1 = "Cannot close a patient during workflow execution!"
mainwindow_wf_executing_error_2 = "Cannot close " + APPNAME + " during workflow execution!"
mainwindow_home_label1 = "Welcome to " + APPNAME + "!"
mainwindow_home_label2 = APPNAME + " (" + app_acronym + ") is a graphic tools for modular neuroimaging processing. " \
                        "With " + APPNAME + " you can easily import and organize DICOM files from multiple sources, " \
                        "generate a pipeline based on available imaging modalities and export results in a " \
                        "multimodal scene."
mainwindow_home_label3 = APPNAME + " does NOT implement processing software but integrates in a user-friendly " \
                        "interface many external applications, so make sure the check the following dependencies."
mainwindow_home_label4 = APPNAME + " is not meant for clinical use!\n"
mainwindow_home_label5 = "\nExternal mandatory dependencies:"
mainwindow_home_label6 = "\nExternal recommended dependencies:"
mainwindow_home_label7 = "\nExternal optional dependencies:"

mainwindow_dep_slicer_src = "Searching Slicer installation..."
mainwindow_dep_slicer_found = "Slicer detected"
mainwindow_pref_disabled_error = "Prefecences disabled during workflow execution!"

menu_load_pt = "Load existing patient"
menu_load_pt_tip = "Load patient data from the main working directory"
menu_new_pt = "Create new patient"
menu_new_pt_tip = "Add a new patient in the main working directory"
menu_exit = "Exit " + APPNAME
menu_pref = "Preferences"
menu_pref_tip = "Edit " + APPNAME + " preferences"
menu_shortcut = "Toggle shortcuts"
menu_about = "About " + APPNAME + "..."
menu_file_name = "File"
menu_tools_name = "Tools"
menu_help_name = "Help"

aboutwindow_python_libs = "Python libraries dependencies: configparser, logging, matplotlib, nipype, pydicom, " \
                          "pyshortcuts, PySide6, psutil"

pttab_data_tab_name = "Data load"
pttab_wf_tab_name = "Workflow execution"
pttab_results_tab_name = "Results export"
pttab_wf_executed = APPNAME + " Workflow executed!"
pttab_wf_executed_with_error = APPNAME + " Workflow finished. Error occurred!"
pttab_import_button = "Import"
pttab_clear_button = "Clear"
pttab_scan_dicom_button = "Scan DICOM folder"
pttab_selected_series_error = "No series was selected"
pttab_wrong_type_check = "Do you want to continue importing?"
pttab_wrong_type_check_msg = "You selected %s images while %s images were expected."
pttab_dicom_copy = "Copying DICOM files in patient folder..."
pttab_dicom_check = "Verifying patient folder..."
pttab_dicom_scan = "Scanning DICOM folder..."
pttab_pt_loading = "Checking patient DICOM folders..."
pttab_select_dicom_folder = 'Select a folder to scan for DICOM files'
pttab_no_dicom_error = "No DICOM file in "
pttab_multi_pt_error = "Dicom file from more than one patient in "
pttab_multi_exam_error = "DICOM file from more than one examination in "
pttab_multi_series_error = "DICOM file from more than one series in "
pttab_missing_fsl_error = "FSL is required to generate " + APPNAME + " Workflow!"
pttab_wf_gen_error = "Error generating the Workflow!"
pttab_old_wf_found = "A previous execution of " + APPNAME + """ was detected. Do you want to resume execution or start 
a new one?"""
pttab_old_wf_resume = "Resume execution"
pttab_old_wf_reset = "New execution"
pttab_old_fs_found = "An existing FreeSurfer folder was detected. Do you want to keep or delete the existing folder?"
pttab_old_fs_resume = "Keep folder"
pttab_old_fs_reset = "Delete folder"
pttab_wf_stop = "Do you REALLY want to stop " + APPNAME + " Workflow execution?"
pttab_results_button = "Export results into Slicer scene"
pttab_exporting_start = "Exporting results into Slicer scene...\nLoading Slicer environment"
pttab_exporting_prefix = "Exporting results into Slicer scene...\n"
pttab_dicom_clearing = "Clearing DICOM files in: "
pttab_wf_insufficient_resources = "Insufficient system resources (RAM or CPU) to execute workflows"

pref_window_title_global = APPNAME + ' - Preferences'
pref_window_title_user = ' - Workflow preferences'

pref_window_global_box_title = "Global settings"
pref_window_global_box_mwd = "Main working directory"
pref_window_global_box_slicer = "3D Slicer path"
pref_window_global_box_default_wf = "Default workflow"
pref_window_global_box_default_task = "Default fMRI taks duration"
pref_window_global_box_pt_limit = "Patient tab limit"
pref_window_global_box_cpu_limit = "CPU per Patient limit"
pref_window_global_box_default_ext = "Slicer scene extension"

pref_window_global_box_optional_title = "Optional series settings"

pref_window_wf_box_title = "Workflow settings"
pref_window_wf_box_reconall = "FreeSurfer analisys"
pref_window_wf_box_reconall_disabled_tip = "FreeSurfer not detected"
pref_window_wf_box_hippo = "FreeSurfer hippocampal subfields"
pref_window_wf_box_hippo_disabled_tip = "Matlab Runtime not detected"
pref_window_wf_box_ai = "Asymmetry Index map for ASL and PET"
pref_window_wf_box_domap = "DOmap analisys"
pref_window_wf_box_tractography = "DTI tractography"
pref_window_wf_box_missing_flair3d = "3D Flair missing"
pref_window_wf_box_missing_dti = "DTI missing"
pref_window_wf_box_missing_ai = "Asymmetry Index maps can be generated for PET or ASL data"

pref_window_fmri_box_task_a_name = "Task A name"
pref_window_fmri_box_task_b_name = "Task B name"
pref_window_fmri_box_task_duration = "Task duration (sec)"
pref_window_fmri_box_rest_duration = "Rest duration (sec)"
pref_window_fmri_box_tr = "TR (sec)"
pref_window_fmri_box_vols = "Number of EPI runs"
pref_window_fmri_box_st = "Slice timing"
pref_window_fmri_box_blockdesign = "Block design"
pref_window_fmri_box_del_start_vols = "Delete start volumes"
pref_window_fmri_box_del_end_vols = "Delete end volumes"

pref_window_tract_box_title = "Tractography settings"

pref_window_save_button = "Save preferences"
pref_window_save_restart_button = "Save preferences (" + APPNAME + " will close and restart)"
pref_window_discard_button = "Discard changes"
pref_window_dir_error = "Directory does not exists!"
pref_window_file_error = "File does not exists!"
pref_window_select_slicer = "Select 3D Slicer executable"

check_dep_dcm2niix_error = "dcm2niix not detected (<a href='https://github.com/rordenlab/dcm2niix#Install" \
                           "'>installation info</a>)"
check_dep_dcm2niix_found = "dcm2niix detected (%s)"
check_dep_fsl_error = "FSL not detected (<a href='https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation" \
                      "'>installation info</a>)"
check_dep_fsl_found = "FSL detected (%s)"
check_dep_fs_found = "FreeSurfer detected (%s)"
check_dep_fs_error1 = "FreeSurfer not detected (<a href='https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall" \
                      "'>installation info</a>)"
check_dep_fs_error2 = "FreeSurfer detected (%s) but without environment configuration"
check_dep_fs_error3 = "FreeSurfer detected (%s). Matlab Runtime is not installed (<a " \
                      "href='https://surfer.nmr.mgh.harvard.edu/fswiki/MatlabRuntime'>registration instruction</a>)"
check_dep_fs_error4 = "FreeSurfer detected (%s). License key missing (<a " \
                      "href='https://surfer.nmr.mgh.harvard.edu/registration.html'>registration instruction</a>)"
check_dep_graph_error = "Graphviz not detected (<a href='https://graphviz.org/download/'>Installation info</a>)"
check_dep_graph_found = "Graphviz detected"
check_dep_slicer_error1 = "Slicer not detected (<a href='https://slicer.readthedocs.io/en/latest/user_guide" \
                          "/getting_started.html#installing-3d-slicer/'>Installation info</a>)"
check_dep_slicer_error2 = "Slicer detected but without SlicerFreeSurfer extension (<a " \
                          "href='https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html?highlight" \
                          "=extension%20manager'>Exstensions Manager info</a>)"
check_dep_slicer_found = "Slicer detected"

fsl_python_error = APPNAME + " has been executed using fsl Python instead of system Python.\nThis may depend " \
                    "on a conflict in FSL(>=6.0.6) and FreeSurfer(<=7.3.2) configurations in your %s file that " \
                    "impacts on correct functioning of " + APPNAME + " and maybe other applications.\n" + APPNAME + \
                    " can try to fix your configuration file or to restart with system Python interpreter. Otherwise" \
                    " you can exit " + APPNAME + " and fix your configuration manually adding this line to your " \
                    "configuration file:"
fsl_python_error_fix = "Fix error and Restart"
fsl_python_error_restart = "Restart with system Python"
fsl_python_error_exit = "Copy fix line and Exit"
generic_shell_file = "your shell configuration"

node_names = {}
node_names["CustomDcm2niix"] = "nifti conversion"
node_names["ForceOrient"] = "standard orientation"
node_names["BET"] = "scalp removal"
node_names["FLIRT"] = "linear registration"
node_names["ApplyXFM"] = "linear transformation"
node_names["FNIRT"] = "nonlinear registration"
node_names["ApplyWarp"] = "nonlinear transformation"
node_names["InvWarp"] = "inverse transformation"
node_names["DataSink"] = "saving"
node_names["ApplyMask"] = "masking"
node_names["EddyCorrect"] = "eddy current correction"
node_names["CustomBEDPOSTX5"] = "diffusion bayesian estimation"
node_names["RandomSeedGenerator"] = "random seeds generation"
node_names["CustomProbTrackX2"] = "probabilistic tractography"
node_names["SumMultiTracks"] = "Parallel tractography merging"
node_names["ReconAll"] = "Freesurfer recon-all"
node_names["CustomLabel2Vol"] = "linear transformation"
node_names["SegmentHA"] = "hippocampal segmentation"
node_names["MCFLIRT"] = "motion correction"
node_names["CustomSliceTimer"] = "slice timing correction"
node_names["SUSAN"] = "noise reduction"
node_names["FMRIGenSpec"] = "functional model generation"
node_names["ArtifactDetect"] = "outliers detection"
node_names["SpecifyModel"] = "functional model application"
node_names["Level1Design"] = "FEAT files generation"
node_names["FEATModel"] = "design file generation"
node_names["FILMGLS"] = "General-Linear-Model estimation"
node_names["SmoothEstimate"] = "smoothness estimation"
node_names["FslCluster"] = "cluster extraction"
node_names["SampleToSurface"] = "surface projection"
node_names["FAST"] = "Tissue segmentation"
node_names["DOmapOutliersMask"] = "outliers mask generation"

