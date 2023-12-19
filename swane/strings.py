# General
APPNAME = "SWANe"
app_acronym = "Standardized Workflow for Advanced Neuroimaging in Epilepsy"
EXECBUTTONTEXT = "Execute " + APPNAME + " Workflow"
EXECBUTTONTEXT_disabled_tooltip = "Generate Workflow first"
EXECBUTTONTEXT_STOP = "Stop " + APPNAME + " Workflow"
GENBUTTONTEXT = "Generate " + APPNAME + " Workflow"
PTCONFIGBUTTONTEXT = "Workflow preferences"
INFOCHAR = "\u24D8"
WF_DIR_SUFFIX = "_nipype"

# Main
main_multiple_instances_error = "Another instance of " + APPNAME + " is already running!"

# Main Window
mainwindow_choose_working_dir = "Choose the main working directory before start to use this application"
mainwindow_working_dir_space_error = "Blank spaces are not allowed in main working dir name or in its parent folder name"
mainwindow_choose_working_dir_title = 'Select the main working directory'
mainwindow_select_pt_folder = 'Select a patient folder'
mainwindow_ptfolder_outside_workingdir_error = "The selected folder is not in " + APPNAME + " main working directory!"
mainwindow_ptfolder_with_blank_spaces_error = "The selected folder name contains blank spaces!"
mainwindow_pt_already_loaded_error = "The selected patient was already loaded in " + APPNAME + "!"
mainwindow_invalid_folder_error = "The selected folder does not contains valid patient data!"
mainwindow_force_dir_update = "If you are SURE you selected a patient folder, " + APPNAME + "can try to update " \
                              "it.\nDo you want to update selected patient folder?"
mainwindow_max_pt_error = "Max patient tab limit reached!"
mainwindow_update_available = "New version available (%s). We recommend you to update " + APPNAME + " with:<br><b><center>pip3 install --upgrade swane"
mainwindow_new_pt_name = 'Write the name of the new patient:'
mainwindow_new_pt_title = 'New patient'
mainwindow_new_pt_created = "New patient created: "
mainwindow_new_pt_name_error = "Invalid name: "
mainwindow_pt_exists_error = "This patient already exists: "
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
mainwindow_pref_disabled_error = "Preferences disabled during workflow execution!"
aboutwindow_python_libs = "Python libraries dependencies: configparser, logging, matplotlib, nipype, pydicom, " \
                          "PySide6, psutil, nibabel, networkx"

# Menu
menu_load_pt = "Load existing patient"
menu_load_pt_tip = "Load patient data from the main working directory"
menu_new_pt = "Create new patient"
menu_new_pt_tip = "Add a new patient in the main working directory"
menu_exit = "Exit " + APPNAME
menu_pref = "Preferences"
menu_pref_tip = "Edit " + APPNAME + " preferences"
menu_wf_pref = "Default Workflow settings"
menu_about = "About " + APPNAME + "..."
menu_file_name = "File"
menu_tools_name = "Tools"
menu_help_name = "Help"

# Patient Tab
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
pttab_wrong_max_vols_check_msg = "The series you selected contains %d volumes while a maximum of %d were expected."
pttab_wrong_min_vols_check_msg = "The series you selected contains %d volumes while a minimum of %d were expected."
pttab_import_copy_error_msg = "Error copying selected series files."
pttab_import_folder_not_empy = "Images are already loaded for this series."
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
pttab_old_wf_found = "This patient has already been analyzed by " + APPNAME + """. Do you want to resume the previous analysis? If you want to delete all
previous analyses and start over press NO, otherwise press YES"""
pttab_old_wf_resume = "Resume execution"
pttab_old_wf_reset = "New execution"
pttab_old_fs_found = "An existing FreeSurfer folder was detected. Do you want to keep or delete the existing folder?"
pttab_old_fs_resume = "Keep folder"
pttab_old_fs_reset = "Delete folder"
pttab_wf_stop = "Do you REALLY want to stop " + APPNAME + " Workflow execution?"
pttab_results_button = "Create/Update Slicer scene " + INFOCHAR
pttab_results_button_tooltip = "In case of a new analysis remember to update the Slicer scene"
pttab_results_button_disabled_tooltip = "Slicer not detected"
pttab_open_results_button = "Visualize scene into Slicer"
pttab_open_results_button_tooltip = "Create a Slicer scene first"
pttab_open_results_directory = "Open result folder"
pttab_exporting_start = "Exporting results into Slicer scene...\nLoading Slicer environment"
pttab_exporting_prefix = "Exporting results into Slicer scene...\n"
pttab_dicom_clearing = "Clearing DICOM files in: "
pttab_wf_insufficient_resources = "Insufficient system resources (RAM or CPU) to execute workflows"
pttab_wf_invalid_signal = "Signaling error, workflow will be stopped. Report this error."
pttab_wf_error_oom_gpu = "Process killed: Out of Memory (GPU). Try to reduce GPU process limit in performance preferences"
pttab_wf_error_oom = "Process killed (possibile Out of Memory). Try to reduce CPU core limit in performance preferences"
pttab_wf_error_terminated = "Process terminated. This can occur if user manually terminates a running process."
pttab_tabtooltip_exec_disabled_series = "A 3D T1w series is required to enable workflow execution"
pttab_tabtooltip_exec_disabled_dependency = "Mandatory dependencies are required to enable workflow execution"
pttab_tabtooltip_result_disabled = "Complete a workflow first"
pttab_tabtooltip_data_disabled = "Cannot change patient data during workflow execution"

# Wf Preference Window
wf_pref_window_title_global = 'Default Workflow Settings'
wf_pref_window_title_user = ' - Workflow Settings'

# Preference Window
pref_window_title_global = APPNAME + ' - Preferences'
pref_window_title_user = ' - Workflow preferences'
pref_window_save_button = "Save preferences"
pref_window_save_restart_button = "Save preferences (" + APPNAME + " will close and restart)"
pref_window_discard_button = "Discard changes"
pref_window_dir_error = "Directory does not exists!"
pref_window_file_error = "File does not exists!"

pref_window_reset_global_button = "Reset workflow settings to default"
pref_window_reset_global_box = "Do you really want to reset global workflow settings to application default?"
pref_window_reset_pt_button = "Apply default workflow settings"
pref_window_reset_pt_box = "Do you really want to apply default workflow settings to this patient?"

# Workflow
check_dep_generic_error = "Dependency check error"
check_dep_dcm2niix_error = "dcm2niix not detected (<a href='https://github.com/rordenlab/dcm2niix#Install" \
                           "'>installation info</a>)"
check_dep_dcm2niix_found = "dcm2niix detected (%s)"
check_dep_fsl_error = "FSL not detected (<a href='https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation" \
                      "'>installation info</a>)"
check_dep_fsl_wrong_version = "FSL version outdated (found %s, required %s). Please " \
                              "<a href='https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation'>update</a>"
check_dep_fsl_found = "FSL detected (%s)"
check_dep_fs_found = "FreeSurfer detected (%s)"
check_dep_fs_error1 = "FreeSurfer not detected (<a href='https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall" \
                      "'>installation info</a>)"
check_dep_fs_error2 = "FreeSurfer detected (%s) but without environment configuration"
check_dep_fs_error3 = "FreeSurfer detected (%s). Matlab Runtime is not installed (<a " \
                      "href='https://surfer.nmr.mgh.harvard.edu/fswiki/MatlabRuntime'>registration instruction</a>)"
check_dep_fs_error4 = "FreeSurfer detected (%s). License key missing (<a " \
                      "href='https://surfer.nmr.mgh.harvard.edu/registration.html'>registration instruction</a>)"
check_dep_fs_wrong_version = "FreeSurfer version outdated (found %s, required %s). Please " \
                              "<a href='https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall'>update</a>"
check_dep_graph_error = "Graphviz not detected (<a href='https://graphviz.org/download/'>Installation info</a>)"
check_dep_graph_found = "Graphviz detected"
check_dep_slicer_error1 = "Slicer not detected (<a href='https://slicer.readthedocs.io/en/latest/user_guide" \
                          "/getting_started.html#installing-3d-slicer/'>Installation info</a>)"
check_dep_slicer_error2 = "Slicer detected but without SlicerFreeSurfer extension (<a " \
                          "href='https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html?highlight" \
                          "=extension%20manager'>Exstensions Manager info</a>)"
check_dep_slicer_wrong_version = "Slicer version outdated (found %s, required %s). Please " \
                              "<a href='https://slicer.readthedocs.io/en/latest/user_guide'>update</a>"
check_dep_slicer_found = "Slicer detected (%s)"

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

# Nodes
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
node_names["EddyCorrect"] = "eddy current correction (old)"
node_names["CustomEddy"] = "eddy current correction"
node_names["GenEddyFiles"] = "eddy current correction preparation"
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
node_names["Cluster"] = "cluster extraction"
node_names["SampleToSurface"] = "surface projection"
node_names["FAST"] = "Tissue segmentation"
node_names["FLAT1OutliersMask"] = "outliers mask generation"
