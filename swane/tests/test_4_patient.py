import os
import shutil
import pytest
import fnmatch
from swane.config.ConfigManager import ConfigManager
from swane.utils.DependencyManager import DependencyManager
from swane.utils.Patient import Patient, PatientRet
from swane.tests import TEST_DIR
from swane.tests.test_3_dicom_search import TestDicomSearchWorker
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.utils.DataInputList import DataInputList


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "patient")
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
    TEST_MAIN_WORKING_DIRECTORY = os.path.join(TEST_DIR, "patient", "subjects")
    TEST_PATIENT_NAME = "pt_01"

    def test_patient(self, global_config, dependency_manager, qtbot):
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

        # Load patient and import
        assert test_patient.load(test_patient_folder) == PatientRet.ValidFolder, "Error loading empty patient"
        series_path = os.path.join(TestDicomSearchWorker.DICOM_DIRS['SINGLE_VOL'][0])
        worker = DicomSearchWorker(series_path)
        worker.run()
        patient_list = worker.get_patient_list()
        exam_list = worker.get_exam_list(patient_list[0])
        series_list = worker.get_series_list(patient_list[0], exam_list[0])
        image_list, patient_name, mod, series_description, vols = worker.get_series_info(patient_list[0], exam_list[0],
                                                                                         series_list[0])
        import_ret = test_patient.dicom_import_to_folder(data_input=DataInputList.T13D, copy_list=image_list, vols=vols,
                                                         mod=mod, force_modality=False)
        assert import_ret == PatientRet.DataImportCompleted, "Importing valid series error"

        test_patient.input_state_list[DataInputList.T13D].loaded = True
        import_ret = test_patient.dicom_import_to_folder(data_input=DataInputList.T13D, copy_list=image_list, vols=vols,
                                                         mod=mod, force_modality=False)
        assert import_ret == PatientRet.DataInputNonEmpty, "Importing in non empty-folder error"

        assert test_patient.dicom_folder_count(DataInputList.T13D) == len(image_list), "Copied files number different from image list length"

        import_ret = test_patient.dicom_import_to_folder(data_input=DataInputList['FMRI_0'], copy_list=image_list, vols=vols,
                                                         mod=mod, force_modality=False)
        assert import_ret == PatientRet.DataImportErrorVolumesMin, "Min volumes check error"

        import_ret = test_patient.dicom_import_to_folder(data_input=DataInputList.FLAIR3D, copy_list=image_list,
                                                         vols=vols, mod="pt", force_modality=False)
        assert import_ret == PatientRet.DataImportErrorModality, "Incorrect modality check error"

        import_ret = test_patient.dicom_import_to_folder(data_input=DataInputList.FLAIR3D, copy_list=image_list,
                                                         vols=vols, mod="pt", force_modality=True)
        assert import_ret == PatientRet.DataImportCompleted, "Incorrect modality force error"
        series_path = os.path.join(TestDicomSearchWorker.DICOM_DIRS['MULTI_VOL'][0])
        worker = DicomSearchWorker(series_path)
        worker.run()
        patient_list = worker.get_patient_list()
        exam_list = worker.get_exam_list(patient_list[0])
        series_list = worker.get_series_list(patient_list[0], exam_list[0])
        image_list, patient_name, mod, series_description, vols = worker.get_series_info(patient_list[0], exam_list[0],
                                                                                         series_list[0])
        import_ret = test_patient.dicom_import_to_folder(data_input=DataInputList.FLAIR3D, copy_list=image_list, vols=vols,
                                                         mod=mod, force_modality=False)
        assert import_ret == PatientRet.DataImportErrorVolumesMax, "Max volumes check error error"

        # clear folder
        clear_ret = test_patient.clear_import_folder(DataInputList.T13D)
        assert clear_ret is True, "Clear folder error"
        assert test_patient.dicom_folder_count(DataInputList.T13D) == 0, "Folder not empty after clear error"

        # with qtbot.waitCallback() as call_back:
        #     test_patient.dicom_import_to_folder(data_input=DataInputList.T13D, copy_list=image_list, vols=vols, mod=mod,
        #                                         force_modality=False, progress_callback=call_back)
        # call_back.assert_called_with(PatientRet.DataImportCompleted)
