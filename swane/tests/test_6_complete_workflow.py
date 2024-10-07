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
    TEST_SUBJECT_NAME = "subj_01"

    def test_complete_workflow(self, qtbot):

        #copy SUBJ_test folder from real swane main working directory to testing folder
        real_global_config = ConfigManager()
        real_main_working_directory = real_global_config.get_main_working_directory()
        real_exec_subject_path = os.path.join(real_main_working_directory, "subj_test")
        assert os.path.exists(real_exec_subject_path), "Could not find subj_test in %s" % real_main_working_directory
        os.system("cp " + real_global_config.config_file + " " + os.getcwd())
        test_global_config = ConfigManager(global_base_folder=os.getcwd())
        test_global_config.set_main_working_directory(TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY)
        os.system("cp -r %s %s" % (real_exec_subject_path, TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY))
        text_exec_subject_path = os.path.join(TestCompleteWorkflow.TEST_MAIN_WORKING_DIRECTORY, "subj_test")
        assert os.path.exists(text_exec_subject_path), "Error in copying subj_test folder"

        # generate test global config
        global_config = ConfigManager(global_base_folder=os.getcwd())

        # start main window
        main_window = MainWindow(global_config)
        qtbot.addWidget(main_window)
        qtbot.waitForWindowShown(main_window)
        main_window.search_subject_dir(folder_path=text_exec_subject_path)
        subj_tab = main_window.main_tab.widget(1)
        assert type(subj_tab) is SubjectTab, "Error in tab selection"
        qtbot.waitUntil(lambda: subj_tab.isTabEnabled(SubjectTab.EXECTAB), timeout=1000 * 60 * 2)
        qtbot.waitUntil(lambda: not subj_tab.is_data_loading(), timeout=1000*60*2)
        assert subj_tab.isTabEnabled(SubjectTab.EXECTAB), "Exectab disabled after data loading"
        subj_tab.setCurrentIndex(SubjectTab.EXECTAB)
        test_subject = subj_tab.subject

        # Clear previous wf output copied from real folder
        shutil.rmtree(test_subject.result_dir(), ignore_errors=True)
        shutil.rmtree(test_subject.graph_dir(), ignore_errors=True)
        shutil.rmtree(os.path.join(text_exec_subject_path, FS_DIR), ignore_errors=True)
        shutil.rmtree(os.path.join(text_exec_subject_path, LOG_DIR_NAME), ignore_errors=True)

        # Generate workflow
        assert subj_tab.generate_workflow_button.isEnabled(), "Generate workflowbutton is disabled"
        qtbot.mouseClick(subj_tab.generate_workflow_button, QtCore.Qt.LeftButton)
        qtbot.waitUntil(lambda: subj_tab.exec_button.isEnabled(), timeout=1000 * 60 * 2)

        # Clear previous wf output copied from real folder
        shutil.rmtree(os.path.join(text_exec_subject_path, test_subject.workflow.name), ignore_errors=True)

        # Execute workflow
        subj_tab.toggle_workflow_execution(False, False)
        qtbot.waitUntil(lambda: test_subject.workflow_monitor_work is not None, timeout=1000*5)
        self.wf_error = False
        test_subject.workflow_monitor_work.signal.log_msg.connect(self.update_node_callback)
        qtbot.waitUntil(lambda: not test_subject.is_workflow_process_alive(), timeout=1000*60*5)
        assert self.wf_error is False, "Node error during workflow"
        assert subj_tab.isTabEnabled(SubjectTab.RESULTTAB), "No result after workflow execution"

        # Generate Slicer Scene
        subj_tab.setCurrentIndex(SubjectTab.RESULTTAB)
        assert subj_tab.generate_scene_button.isEnabled(), "Generate scene button not enabled"
        assert subj_tab.open_results_directory_button.isEnabled(), "Open result button not enabled"
        progress_dialog = subj_tab.generate_scene()
        qtbot.waitUntil(lambda: not progress_dialog.isVisible(), timeout=1000 * 60 * 25)
        assert subj_tab.load_scene_button.isEnabled(), "Load scene button not enabled"

        # Show scene in slicer
        qtbot.mouseClick(subj_tab.load_scene_button, QtCore.Qt.LeftButton)

    def update_node_callback(self, wf_report: WorkflowReport):
        if wf_report.signal_type == WorkflowSignals.NODE_ERROR:
            self.wf_error = True
