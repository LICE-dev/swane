import os
import shutil
import pytest
from swane.config.ConfigManager import ConfigManager
from swane.utils.DependencyManager import DependencyManager
from swane.utils.Patient import Patient, PatientRet


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = TestPatient.TEST_DIR
    test_main_working_directory = TestPatient.TEST_MAIN_WORKING_DIRECTORY
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.makedirs(test_main_working_directory, exist_ok=True)
    os.chdir(test_dir)


@pytest.fixture()
def global_config():
    global_config = ConfigManager(global_base_folder=os.getcwd())
    global_config.set_main_working_directory(TestPatient.TEST_MAIN_WORKING_DIRECTORY)
    return global_config


@pytest.fixture()
def dependency_manager():
    return DependencyManager()


class TestPatient:
    TEST_DIR = os.path.join(os.path.expanduser("~"), "swane_test")
    TEST_MAIN_WORKING_DIRECTORY = os.path.join(TEST_DIR, "subjects")
    TEST_PATIENT_NAME = "pt_01"

    def test_patient(self, monkeypatch, global_config, dependency_manager):
        assert global_config.get_main_working_directory() == TestPatient.TEST_MAIN_WORKING_DIRECTORY, "Bad global config fixture"

        # Testing creation of new patient
        test_patient = Patient(global_config, dependency_manager)
        assert test_patient.create_new_patient_dir("Invalid with space") == PatientRet.PathBlankSpaces, "Error with new patient with blank space"
        assert test_patient.create_new_patient_dir("Invalid*char") == PatientRet.PathBlankSpaces, "Error with new patient with special character"
        assert test_patient.create_new_patient_dir(None) == PatientRet.FolderNotFound, "Error with new patient with None name"
        assert test_patient.create_new_patient_dir("") == PatientRet.FolderNotFound, "Error with new patient with empty name"
        assert test_patient.create_new_patient_dir(TestPatient.TEST_PATIENT_NAME) == PatientRet.ValidFolder, "Error with new patient with valid name"
        assert test_patient.create_new_patient_dir(TestPatient.TEST_PATIENT_NAME) == PatientRet.FolderAlreadyExists, "Error with new patient with already existing name"
        test_patient_folder = test_patient.folder

        # Testing function check_pt_folder
        test_patient = Patient(global_config, dependency_manager)
        path_with_spaces = os.path.join(TestPatient.TEST_MAIN_WORKING_DIRECTORY, "pt space")
        assert test_patient.check_patient_folder(path_with_spaces) == PatientRet.FolderNotFound, "Error with non existing folder"
        os.makedirs(path_with_spaces)
        assert test_patient.check_patient_folder(path_with_spaces) == PatientRet.PathBlankSpaces, "Error with path containing blank spaces"
        assert test_patient.check_patient_folder(os.path.expanduser("~")) == PatientRet.FolderOutsideMain, "Error with folder outside main working directory"
        path_without_subtree = os.path.join(TestPatient.TEST_MAIN_WORKING_DIRECTORY, "pt_without_subtree")
        os.makedirs(path_without_subtree)
        assert test_patient.check_patient_folder(path_without_subtree) == PatientRet.InvalidFolderTree, "Error with folder without subtree"
        assert test_patient.check_patient_folder(test_patient_folder) == PatientRet.ValidFolder, "Error loading a patient valid folder"
        # Test restoring a corrupted patient subtree with fix_patient_folder_subtree
        test_patient.fix_patient_folder_subtree(path_without_subtree)
        assert test_patient.check_patient_folder(path_without_subtree) == PatientRet.ValidFolder, "Error fixing patient subtree"




