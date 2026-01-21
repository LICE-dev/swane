# General
APPNAME = "SWANe"
app_acronym = "Standardized Workflow for Advanced Neuroimaging in Epilepsy"
EXECBUTTONTEXT = "Execute " + APPNAME + " Workflow"
EXECBUTTONTEXT_disabled_tooltip = "Generate Workflow first"
EXECBUTTONTEXT_STOP = "Stop " + APPNAME + " Workflow"
GENBUTTONTEXT = "Generate " + APPNAME + " Workflow"
SUBJCONFIGBUTTONTEXT = "Workflow preferences"
INFOCHAR = "\u24d8"
WF_DIR_SUFFIX = "_nipype"
WIKI_URL = "https://github.com/LICE-dev/swane/wiki"

# Main
main_multiple_instances_error = (
    "Another instance of " + APPNAME + " is already running!"
)

# Main Window
mainwindow_choose_working_dir = (
    "Choose the main working directory before start to use this application"
)
mainwindow_working_dir_space_error = (
    "Blank spaces are not allowed in main working dir name or in its parent folder name"
)
mainwindow_choose_working_dir_title = "Select the main working directory"
mainwindow_select_subj_folder = "Select a subject folder"
mainwindow_subj_folder_outside_workingdir_error = (
    "The selected folder is not in " + APPNAME + " main working directory!"
)
mainwindow_subj_folder_with_blank_spaces_error = (
    "The selected folder name contains blank spaces!"
)
mainwindow_subj_already_loaded_error = (
    "The selected subject was already loaded in " + APPNAME + "!"
)
mainwindow_invalid_folder_error = (
    "The selected folder does not contains valid subject data!"
)
mainwindow_force_dir_update = (
    "If you are SURE you selected a subject folder, " + APPNAME + " can try to update "
    "it.\nDo you want to update selected subject folder?"
)
mainwindow_max_subj_error = "Max subject tab limit reached!"
mainwindow_update_available = (
    "New version available (%s). We recommend you to update "
    + APPNAME
    + " with:<br><b><center>pip3 install --upgrade swane"
)
mainwindow_new_subj_name = "Write the name of the new subject:"
mainwindow_new_subj_title = "New subject"
mainwindow_new_subj_created = "New subject created: "
mainwindow_new_subj_name_error = "Invalid name: "
mainwindow_subj_exists_error = "This subject already exists: "
mainwindow_home_tab_name = "Home"
mainwindow_wf_executing_error_1 = "Cannot close a subject during workflow execution!"
mainwindow_wf_executing_error_2 = (
    "Cannot close " + APPNAME + " during workflow execution!"
)
mainwindow_home_label1 = "Welcome to " + APPNAME + "!"
mainwindow_home_label2 = (
    APPNAME
    + " ("
    + app_acronym
    + ") is a graphic tools for modular neuroimaging processing. "
    "With "
    + APPNAME
    + " you can easily import and organize DICOM files from multiple sources, "
    "generate a pipeline based on available imaging modalities and export results in a "
    "multimodal scene."
)
mainwindow_home_label3 = (
    APPNAME
    + " does NOT implement processing software but integrates in a user-friendly "
    "interface many external applications, so make sure the check the following dependencies."
)
mainwindow_home_label4 = APPNAME + " is not meant for clinical use!\n"
mainwindow_home_label5 = "\nExternal mandatory dependencies:"
mainwindow_home_label6 = "\nExternal recommended dependencies:"
mainwindow_home_label7 = "\nExternal optional dependencies:"

mainwindow_dep_slicer_src = "Searching Slicer installation..."
mainwindow_pref_disabled_error = "Preferences disabled during workflow execution!"
aboutwindow_wiki_dependencylist = "Link to <a href='https://github.com/LICE-dev/swane/wiki/04-Dependencies-Guides'>dependencies list</a>"
aboutwindow_wiki_changelog = "Link to versions <a href='https://github.com/LICE-dev/swane/wiki/11-Changelog'>changelog</a>"

mainwindow_chatgpt_title = "SWANe Assistant"
mainwindow_chatgpt_tooltip = "Open ChatGPT SWANe Assistant in your browser"
chatgpt_url = "https://chatgpt.com/g/g-68e14421a54c8191a2110a831824f1e9-swaneassistant/"
chatgpt_button_text = f"🤖 {mainwindow_chatgpt_title}"

# Menu
menu_load_subj = "&Load subject..."
menu_load_subj_tip = "Load subject data from the main working directory"
menu_new_subj = "&New subject..."
menu_new_subj_tip = "Add a new subject in the main working directory"
menu_exit = "E&xit " + APPNAME
menu_pref = "Application &Settings..."
menu_pref_tip = "Edit " + APPNAME + " settings"
menu_start_preference_wizard = "Configuration &Wizard..."
menu_wf_pref = "Default Workflow &Preferences..."
menu_shutdown_pref = "Shutdown at Workflow end"
menu_about = "&About " + APPNAME + "..."
menu_wiki = "Visit " + APPNAME + " &Wiki..."
menu_file_name = "File"
menu_tools_name = "Tools"
menu_help_name = "Help"
menu_auto_import = "Automatic series classification"

# Subject Tab
subj_tab_data_tab_name = "Data load"
subj_tab_wf_tab_name = "Workflow execution"
subj_tab_results_tab_name = "Results export"
subj_tab_wf_executed = APPNAME + " Workflow executed!"
subj_tab_wf_executed_with_error = APPNAME + " Workflow finished. Error occurred!"
subj_tab_import_button = "Import"
subj_tab_clear_button = "Clear"
subj_tab_scan_dicom_button = "Scan DICOM folder"
subj_tab_selected_series_error = "No series was selected"
subj_tab_wrong_type_check = "Do you want to continue importing?"
subj_tab_wrong_type_check_msg = "You selected %s images while %s images were expected."
subj_tab_wrong_max_vols_check_msg = (
    "The series you selected contains %d volumes while a maximum of %d were expected."
)
subj_tab_wrong_min_vols_check_msg = (
    "The series you selected contains %d volumes while a minimum of %d were expected."
)
subj_tab_import_copy_error_msg = "Error copying selected series files."
subj_tab_import_folder_not_empy = "Images are already loaded for this series."
subj_tab_found_series_type = "{series_description} could be associated with input {data_label}.\nDou you want to import it?"
subj_tab_dicom_copy = "Copying DICOM files in subject folder..."
subj_tab_dicom_check = "Verifying subject folder..."
subj_tab_dicom_scan = "Scanning folder for primary non derived DICOM images..."
subj_tab_subj_loading = "Checking subject DICOM folders..."
subj_tab_select_dicom_folder = "Select a folder to scan for DICOM files"
subj_tab_no_dicom_error = "No DICOM file in "
subj_tab_multi_subj_error = "Dicom file from more than one subject in "
subj_tab_multi_exam_error = "DICOM file from more than one examination in "
subj_tab_multi_series_error = "DICOM file from more than one series in "
subj_tab_missing_fsl_error = "FSL is required to generate " + APPNAME + " Workflow!"
subj_tab_wf_gen_error = "Error generating the Workflow!"
subj_tab_old_wf_found = (
    "This subject has already been analyzed by "
    + APPNAME
    + """. Do you want to resume the previous analysis? If you want to delete all
previous analyses and start over press NO, otherwise press YES"""
)
subj_tab_old_wf_resume = "Resume execution"
subj_tab_old_wf_reset = "New execution"
subj_tab_old_fs_found = "An existing FreeSurfer folder was detected. Do you want to keep or delete the existing folder?"
subj_tab_old_fs_resume = "Keep folder"
subj_tab_old_fs_reset = "Delete folder"
subj_tab_wf_stop = "Do you REALLY want to stop " + APPNAME + " Workflow execution?"
subj_tab_generate_scene_button = "Create/Update Slicer scene " + INFOCHAR
subj_tab_generate_scene_button_tooltip = (
    "In case of a new analysis remember to update the Slicer scene"
)
subj_tab_generate_scene_button_disabled_tooltip = "Slicer not detected"
subj_tab_load_scene_button = "Visualize scene into Slicer"
subj_tab_load_scene_button_tooltip = "Create a Slicer scene first"
subj_tab_open_results_directory = "Open results folder"
subj_tab_exporting_start = (
    "Exporting results into Slicer scene...\nLoading Slicer environment"
)
subj_tab_exporting_prefix = "Exporting results into Slicer scene...\n"
subj_tab_dicom_clearing = "Clearing DICOM files in: "
subj_tab_wf_insufficient_resources = (
    "Insufficient system resources (RAM or CPU) to execute workflows"
)
subj_tab_wf_invalid_signal = (
    "Signaling error, workflow will be stopped. Report this error."
)
subj_tab_wf_error_oom_gpu = "Process killed: Out of Memory (GPU). Try to reduce GPU process limit in performance preferences"
subj_tab_wf_error_oom = "Process killed (possible Out of Memory). Try to reduce CPU core limit in performance preferences"
subj_tab_wf_error_terminated = (
    "Process terminated. This can occur if user manually terminates a running process."
)
subj_tab_tabtooltip_exec_disabled_series = (
    "A 3D T1w series is required to enable workflow execution"
)
subj_tab_tabtooltip_exec_disabled_dependency = (
    "Mandatory dependencies are required to enable workflow execution"
)
subj_tab_tabtooltip_result_disabled = "Complete a workflow first"
subj_tab_tabtooltip_data_disabled = (
    "Cannot change subject data during workflow execution"
)
subj_tab_unsupported_files = (
    APPNAME
    + " works on primary non derived DICOM images.\nFolder contains ImageType combinations that are not accepted: {}"
)

sub_tab_node_name_label = "Node"
sub_tab_node_status_label = "Status"
sub_tab_node_status_not_started = "Not started"
sub_tab_node_status_running = "Execution started at"
sub_tab_node_status_completed = "Completed at"
sub_tab_node_status_failed = "Failed"
sub_tab_node_dir_label = "Directory"
sub_tab_node_crash_label = "Crash file"
sub_tab_node_command_label = "Command"
sub_tab_node_duration_label = "Duration"
sub_tab_node_cpu_label = "CPU %"
sub_tab_node_ram_label = "Mem (GB)"
sub_tab_node_output_label = "Output"
sub_tab_node_slicer_button_tooltip = "Open in 3D Slicer"
sub_tab_node_file_button_tooltip = "Show in File Manager"

# Wf Preference Window
wf_pref_window_title_user = " - Workflow preferences"

# Preference Window
pref_window_save_button = "Save preferences"
pref_window_save_restart_button = (
    "Save preferences (" + APPNAME + " will close and restart)"
)
pref_window_discard_button = "Discard changes"
pref_window_dir_error = "Directory does not exists!"
pref_window_file_error = "File does not exists!"

pref_window_reset_global_button = "Reset workflow settings to default"
pref_window_reset_global_box = (
    "Do you really want to reset global workflow settings to application default?"
)
pref_window_reset_subj_button = "Apply default workflow settings"
pref_window_reset_subj_box = (
    "Do you really want to apply default workflow settings to this subject?"
)

pref_window_mail_test_button = "Test email settings"
pref_window_mail_test_hint = "By clicking this button a test mail wil be send using the mail settings preferences"
pref_window_mail_test_fail = (
    "An error occurred, check " + APPNAME + " mail configuration"
)
pref_window_mail_test_success = "Mail sent succesfully, check in your inbox"

# Preference Wizard Window
preference_wizard_title = APPNAME + " Configuration Wizard"
wizard_apply_button = "&Apply"
wizard_back_button = "&Back"
wizard_next_button = "&Next"
wizard_finish_button = "&Finish"
wizard_cancel_button = "&Cancel"
wizard_start_button = "&Get Started"

wizard_welcome_title = "Welcome to the " + APPNAME + " Configuration Wizard"
wizard_welcome_text = (
    "This wizard will guide you through selecting the optimal computational settings "
    "for your research workflows.\n\n"
    "It helps balance performance, resource usage, and advanced features so that SWANe can "
    "analyze your data efficiently and reliably.\n\n"
    "You’ll be able to:\n"
    "• Select a performance profile that matches your priorities.\n"
    "• Enable hardware acceleration, if supported.\n"
    "• Choose whether to use advanced models for improved results.\n"
    "• Select Freesurfer output of your interest, if supported.\n"
    "• Review a summary of your configuration before applying it.\n\n"
    "These settings can always be adjusted later in Application Settings, or you can rerun "
    "this wizard at any time from Menu → Configuration Wizard."
)

wizard_performance_title = "Choose your performance profile"
wizard_performance_text = (
    "This helps "
    + APPNAME
    + " optimize processing based on your system capabilities and research needs."
)
performance_profile_max = "Maximum Performance"
performance_profile_max_tooltip = (
    "Use more system resources to complete tasks as quickly as possible."
)
performance_profile_balanced = "Balanced"
performance_profile_balanced_tooltip = (
    "A compromise between speed and resource usage for most analyses."
)
performance_profile_min = "Minimum Resource Usage"
performance_profile_min_tooltip = "Minimize CPU and memory usage to keep the system responsive, even on limited hardware."

wizard_hardware_accelleration_title = "Hardware Accelleration"
wizard_hardware_accelleration_text = (
    "Speed up computations by using supported hardware features."
)
gpu_acceleration_enabled = "Use GPU acceleration when available"
gpu_acceleration_enabled_tooltip = (
    "This can accelerate advanced computations if the GPU is supported by your system."
)
gpu_acceleration_disabled = "CPU only"
gpu_acceleration_disabled_tooltip = (
    "All processing will run on the CPU, even if GPU acceleration is available."
)

wizard_advanced_models_title = "Advanced Models"
wizard_advanced_models_text = (
    "Advanced models implement state-of-the-art FreeSurferdeep learning algorithms (Synth Tools) that can improve results "
    "and, in some cases, reduce analysis time.\n"
    "They may require additional memory and processing power."
)
advanced_models_enabled = "Use advanced models when supported"
advanced_models_enabled_tooltip = (
    "Enable advanced models when the system can handle them reliably."
)
advanced_models_disabled = "Use standard models only"
advanced_models_disabled_tooltip = (
    "Prefer lighter, more stable processing techniques with minimal resource usage."
)

wizard_freesurfer_outputs_title = "FreeSurfer Outputs Selection"
wizard_freesurfer_outputs_tooltip = (
    "Select which FreeSurfer outputs you want to generate for your analyses.\n"
    "You can choose multiple options or none.\n"
    "More selections will increase processing time."
)
freesurfer_outputs_cortical_parcellation = "Cortical Parcellation"
freesurfer_outputs_cortical_parcellation_tooltip = (
    "Generates cortical parcellation maps using FreeSurfer's standard methods."
)
freesurfer_outputs_surfaces = "Surfaces"
freesurfer_outputs_surfaces_tooltip = "Produces white matter and pial 3D models surface models for surface-based analyses."
freesurfer_outputs_hippocampal_segmentation = (
    "Hippocampal/Amigdala Subfield Segmentation"
)
freesurfer_outputs_hippocampal_segmentation_tooltip = "Produces detailed hippocampal and amigdala subfields segmentation for advanced analyses."
freesurfer_full_reconall = "Full Recon-All Processing"
freesurfer_full_reconall_tooltip = (
    "Enables the complete Recon-All pipeline for comprehensive brain analysis."
)

wizard_review_title = "Review Your Configuration"
wizard_review_text = "Please review your selections before applying them."
wizard_review_tooltip = (
    "Some options may be automatically adjusted to ensure stability and compatibility."
)

wizard_applied_title = "Configuration applied successfully"
wizard_applied_text = (
    "Your settings have been applied.<br><br>"
    "These settings may influence analysis performance and memory usage.<br>"
    "You can always adjust them in more detail via Application Settings.<br><br>"
    "For additional guidance, documentation, and troubleshooting, visit the <a href='"
    + WIKI_URL
    + "'>SWANe Wiki</a>.<br>"
    "You can also rerun this wizard at any time from Menu → Configuration Wizard."
)

wizard_selected_profile = "<b>Selected profile</b>: {profile}"
wizard_gpu_accelleration = "<b>GPU acceleration</b>: {gpu_status}"
wizard_advanced_models = "<b>Advanced models</b>: {adv_status}"
wizard_freesurfer_outputs = "<b>FreeSurfer outputs</b>: {fs_outputs}"

# Workflow
check_dep_generic_error = "Dependency check error"
check_dep_dcm2niix_error = (
    "dcm2niix not detected (<a href='https://github.com/rordenlab/dcm2niix#Install"
    "'>installation info</a>)"
)
check_dep_dcm2niix_found = "dcm2niix detected (%s)"
check_dep_fsl_error = (
    "FSL not detected (<a href='https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation"
    "'>installation info</a>)"
)
check_dep_fsl_wrong_version = (
    "FSL version outdated (found %s, required %s). Please "
    "<a href='https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation'>update</a>"
)
check_dep_fsl_no_locale = (
    "FSL detected, but locale en_US.utf8 not available. Use: sudo locale-gen en_US.utf8"
)
check_dep_fsl_found = "FSL detected (%s)"
check_dep_fs_found = "FreeSurfer detected (%s)"
check_dep_fs_error1 = (
    "FreeSurfer not detected (<a href='https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall"
    "'>installation info</a>)"
)
check_dep_fs_error2 = "FreeSurfer detected (%s), but without environment configuration"
check_dep_fs_error3 = (
    "FreeSurfer detected (%s). OPTIONAL: install Matlab Runtime (<a "
    "href='https://surfer.nmr.mgh.harvard.edu/fswiki/MatlabRuntime'>instructions</a>)"
)
check_dep_fs_error4 = (
    "FreeSurfer detected (%s). License key missing (<a "
    "href='https://surfer.nmr.mgh.harvard.edu/registration.html'>registration instructions</a>)"
)
check_dep_fs_outdated_version = (
    "FreeSurfer version outdated (found %s, required %s). Please "
    "<a href='https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall'>update</a>"
)
check_dep_fs_synth_version = (
    "FreeSurfer detected (found %s, recommended %s). Please "
    "<a href='https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall'>update</a> to speed up processing greatly."
)
check_dep_fs_no_tcsh = "FreeSurfer detected (%s), but tcsh is not installed."
check_dep_fs_low_ram = (
    "FreeSurfer detected (%s). With less than %dGB of RAM, processing will be slower."
)
check_dep_graph_error = "Graphviz not detected (<a href='https://graphviz.org/download/'>Installation info</a>)"
check_dep_graph_found = "Graphviz detected"
check_dep_slicer_error1 = (
    "Slicer not detected (<a href='https://slicer.readthedocs.io/en/latest/user_guide"
    "/getting_started.html#installing-3d-slicer/'>Installation info</a>)"
)
check_dep_slicer_error2 = (
    "Required Slicer modules (%s) are missing (<a "
    "href='https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html?highlight"
    "=extension%%20manager'>Extensions Manager info</a>)"
)
check_dep_slicer_wrong_version = (
    "Slicer version outdated (found %s, required %s). Please "
    "<a href='https://slicer.readthedocs.io/en/latest/user_guide'>update</a>"
)
check_dep_slicer_found = "Slicer detected (%s)"

fsl_python_error = (
    APPNAME
    + " has been executed using fsl Python instead of system Python.\nThis may depend "
    "on a conflict in FSL(>=6.0.6) and FreeSurfer(<=7.3.2) configurations in your %s file that "
    "impacts on correct functioning of "
    + APPNAME
    + " and maybe other applications.\n"
    + APPNAME
    + " can try to fix your configuration file or to restart with system Python interpreter. Otherwise"
    " you can exit "
    + APPNAME
    + " and fix your configuration manually adding this line to your "
    "configuration file:"
)
fsl_python_error_fix = "Fix error and Restart"
fsl_python_error_restart = "Restart with system Python"
fsl_python_error_exit = "Copy fix line and Exit"
generic_shell_file = "your shell configuration"

# Nodes
node_names = {}
node_names["CustomDcm2niix"] = "nifti conversion"
node_names["RobustFOV"] = "neck removal"
node_names["ForceOrient"] = "standard orientation"
node_names["BET"] = "scalp removal"
node_names["SegmentEndocranium"] = "scalp removal"
node_names["SynthStrip"] = "scalp removal"
node_names["SynthMorphReg"] = "registration"
node_names["SynthSeg"] = "SynthSeg cortical parcellation"
node_names["FLIRT"] = "linear registration"
node_names["ApplyXFM"] = "linear transformation"
node_names["SynthMorphApply"] = "linear transformation"
node_names["FNIRT"] = "nonlinear registration"
node_names["ApplyWarp"] = "nonlinear transformation"
node_names["InvWarp"] = "inverse transformation"
node_names["DataSink"] = "saving"
node_names["ApplyMask"] = "masking"
node_names["EddyCorrect"] = "eddy current correction (old)"
node_names["CustomEddy"] = "eddy current correction"
node_names["GenEddyFiles"] = "eddy current correction preparation"
node_names["BEDPOSTX5"] = "diffusion bayesian estimation"
node_names["RandomSeedGenerator"] = "random seeds generation"
node_names["CustomProbTrackX2"] = "probabilistic tractography"
node_names["SumMultiTracks"] = "Parallel tractography merging"
node_names["ReconAll"] = "Recon-all"
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
node_names["MELODIC"] = "Melodic - IC Analysis"
node_names["SelectFiles"] = "Melodic - Output selection"
node_names["FeatureSpatialPrep"] = "Aroma - Preprocessing"
node_names["FeatureSpatial"] = "Aroma - Spatial feature"
node_names["FeatureTimeSeries"] = "Aroma - Time feature"
node_names["FeatureFrequency"] = "Aroma - Frequency feature"
node_names["AromaClassification"] = "Aroma - Noise classification"
node_names["FilterRegressor"] = "Aroma - Denoising"
node_names["FeatureFrequency"] = "Aroma - Frequency feature"
node_names["FeatureFrequency"] = "Aroma - Frequency feature"
