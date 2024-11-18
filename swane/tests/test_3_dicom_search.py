import os
import shutil
import pytest
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.tests import TEST_DIR


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "dicom")
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)


class TestDicomSearchWorker:
    GENERIC_DICOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dicom")
    DICOM_DIRS = {
        # [path, files number, patient, exams, series, vols, series file number]
        'EMPTY_FOLDER': [os.path.join(GENERIC_DICOM_DIR, "empty_folder"), 0, 0, 0, 0, 0, 0],
        'SINGLE_VOL': [os.path.join(GENERIC_DICOM_DIR, "singlevol"), 11, 1, 1, 1, 1, 11],
        'TWO_VOL': [os.path.join(GENERIC_DICOM_DIR, "twovol"), 10, 1, 1, 1, 2, 10],
        'MULTI_VOL': [os.path.join(GENERIC_DICOM_DIR, "multivol"), 12, 1, 1, 1, 4, 12],
        'NONDICOM': [os.path.join(GENERIC_DICOM_DIR, "non_dicom_files"), 2, 0, 0, 0, 0, 0],
        'MULTI_SUBJ': [os.path.join(GENERIC_DICOM_DIR, "multisubj"), 4, 2, -1, -1, -1, -1],
        'MULTI_EXAM': [os.path.join(GENERIC_DICOM_DIR, "multiexam"), 2, 1, 2, -1, -1, 1],
    }

    def test_dicom_search(self):
        os.makedirs(TestDicomSearchWorker.DICOM_DIRS['EMPTY_FOLDER'][0], exist_ok=True)
        for test in TestDicomSearchWorker.DICOM_DIRS.values():
            test_name = os.path.basename(test[0])
            assert os.path.exists(test[0]) is True, "Dicom dir not found %s" % test_name
            worker = DicomSearchWorker(test[0])
            worker.run()
            # numer of files to scan
            if test[1] != -1:
                assert worker.get_files_len() == test[1], "Error with file count for %s (expected %d got %d)" % (test_name, test[1], worker.get_files_len())
            # patients number
            patient_list = worker.tree.get_subject_list()
            if test[2] != -1:
                assert len(patient_list) == test[2], "Error with patient number for %s (expected %d got %d)" % (test_name, test[2], len(patient_list))
            if len(patient_list) > 0:
                studies_list = worker.tree.get_studies_list(patient_list[0])
                if test[3] != -1:
                    assert len(studies_list) == test[3], "Error with exam number for %s (expected %d got %d)" % (test_name, test[3], len(studies_list))
                if len(studies_list) > 0:
                    series_list = worker.tree.get_series_list(patient_list[0], studies_list[0])
                    if test[4] != -1:
                        assert len(series_list) == test[4], "Error with series number for %s (expected %d got %d)" % (test_name, test[4], len(series_list))
                    if len(series_list) > 0:
                        vols = worker.tree.get_series(patient_list[0], studies_list[0], series_list[0]).volumes
                        if test[5] != -1:
                            assert vols == test[5], "Error with series volumes for %s (expected %d got %d)" % (test_name, test[5], vols)
                        series_files = len(worker.tree.get_series(patient_list[0], studies_list[0], series_list[0]).dicom_locs)
                        if test[6] != -1:
                            assert series_files == test[6], "Error with series number of files for %s" % test_name
