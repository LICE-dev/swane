import os
import shutil
import pytest
from swane.config.ConfigManager import ConfigManager
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
from swane.workers.WorkflowProcess import LOG_DIR_NAME
from swane.tests import TEST_DIR
from swane.nipype_pipeline.workflows.freesurfer_workflow import FS_DIR
from swane.ui.MainWindow import MainWindow
from swane.ui.SubjectTab import SubjectTab
from PySide6 import QtCore


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "complete_workflow")
    test_main_working_directory = TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.makedirs(test_main_working_directory, exist_ok=True)
    os.chdir(test_dir)


class TestCompleteWorkflow:
    TEST_MAIN_WORKING_DIRECTORY = os.path.join(TEST_DIR, "complete_workflow", "subjects")
    TEST_PATIENT_NAME = "pt_01"

    def test_complete_workflow(self, qtbot):

        #copy pt_test folder from real swane main working directory to testing folder
        real_global_config = ConfigManager()
        real_main_working_directory = real_global_config.get_main_working_directory()
        real_exec_patient_path = os.path.join(real_main_working_directory, "pt_test")
        assert os.path.exists(real_exec_patient_path), "Could not find pt_test in %s" % real_main_working_directory
        os.system("cp " + real_global_config.config_file + " " + os.getcwd())
        test_global_config = ConfigManager(global_base_folder=os.getcwd())
        test_global_config.set_main_working_directory(TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY)
        os.system("cp -r %s %s" % (real_exec_patient_path, TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY))
        text_exec_patient_path = os.path.join(TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY, "pt_test")
        assert os.path.exists(text_exec_patient_path), "Error in copying pt_test folder"

        # generate test global config
        global_config = ConfigManager(global_base_folder=os.getcwd())

        # start main window
        main_window = MainWindow(global_config)
        qtbot.addWidget(main_window)
        qtbot.waitForWindowShown(main_window)
        main_window.search_subject_dir(folder_path=text_exec_patient_path)
        pt_tab = main_window.main_tab.widget(1)
        assert type(pt_tab) is SubjectTab, "Error in tab selection"
        qtbot.waitUntil(lambda: pt_tab.isTabEnabled(SubjectTab.EXECTAB), timeout=1000 * 60 * 2)
        qtbot.waitUntil(lambda: not pt_tab.is_data_loading(), timeout=1000*60*2)
        assert pt_tab.isTabEnabled(SubjectTab.EXECTAB), "Exectab disabled after data loading"
        pt_tab.setCurrentIndex(SubjectTab.EXECTAB)
        test_patient = pt_tab.subject

        # Clear previous wf output copied from real folder
        shutil.rmtree(test_patient.result_dir(), ignore_errors=True)
        shutil.rmtree(test_patient.graph_dir(), ignore_errors=True)
        shutil.rmtree(os.path.join(text_exec_patient_path, FS_DIR), ignore_errors=True)
        shutil.rmtree(os.path.join(text_exec_patient_path, LOG_DIR_NAME), ignore_errors=True)

        # Generate workflow
        assert pt_tab.generate_workflow_button.isEnabled(), "Generate workflowbutton is disabled"
        qtbot.mouseClick(pt_tab.generate_workflow_button, QtCore.Qt.LeftButton)
        qtbot.waitUntil(lambda: pt_tab.exec_button.isEnabled(), timeout=1000 * 60 * 2)

        # Clear previous wf output copied from real folder
        shutil.rmtree(os.path.join(text_exec_patient_path, test_patient.workflow.name), ignore_errors=True)

        # Execute workflow
        pt_tab.toggle_workflow_execution(False, False)
        qtbot.waitUntil(lambda: test_patient.workflow_monitor_work is not None, timeout=1000*5)
        self.wf_error = False
        test_patient.workflow_monitor_work.signal.log_msg.connect(self.update_node_callback)
        qtbot.waitUntil(lambda: not test_patient.is_workflow_process_alive(), timeout=1000*60*5)
        assert self.wf_error is False, "Node error during workflow"
        assert pt_tab.isTabEnabled(SubjectTab.RESULTTAB), "No result after workflow execution"

        # Generate Slicer Scene
        pt_tab.setCurrentIndex(SubjectTab.RESULTTAB)
        assert pt_tab.generate_scene_button.isEnabled(), "Generate scene button not enabled"
        assert pt_tab.open_results_directory_button.isEnabled(), "Open result button not enabled"
        progress_dialog = pt_tab.generate_scene()
        qtbot.waitUntil(lambda: not progress_dialog.isVisible(), timeout=1000 * 60 * 25)
        assert pt_tab.load_scene_button.isEnabled(), "Load scene button not enabled"

        # Show scene in slicer
        qtbot.mouseClick(pt_tab.load_scene_button, QtCore.Qt.LeftButton)

    def update_node_callback(self, wf_report: WorkflowReport):
        if wf_report.signal_type == WorkflowSignals.NODE_ERROR:
            self.wf_error = True
