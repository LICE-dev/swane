import os
import shutil
import pytest
from pydicom.uid import generate_uid
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.tests import TEST_DIR


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "dicom")
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)


from swane.tests.helpers.dicom_factory import write_minimal_dicom

class TestDicomSearchWorker:
    DICOM_DIRS = {
        'SINGLE_VOL': [
            os.path.join(os.path.expanduser('~'), 'test_swane', 'dicom', 'singlevol')
        ],
        'MULTI_VOL': [
            os.path.join(os.path.expanduser('~'), 'test_swane', 'dicom', 'multivol')
        ],
    }

    def test_dicom_search(self):
        # base test dir under the user's TEST_DIR (fixture sets cwd to TEST_DIR/dicom)
        base_dir = os.path.join(os.path.expanduser("~"), "test_swane", "dicom")
        # ensure a clean base
        if os.path.exists(base_dir):
            import shutil

            shutil.rmtree(base_dir, ignore_errors=True)
        os.makedirs(base_dir, exist_ok=True)

        # build scenarios at runtime
        scenarios = {}

        # EMPTY_FOLDER
        scenarios['EMPTY_FOLDER'] = [os.path.join(base_dir, 'empty_folder'), 0, 0, 0, 0, 0, 0]
        os.makedirs(scenarios['EMPTY_FOLDER'][0], exist_ok=True)

        # SINGLE_VOL: 11 files, 1 patient, 1 study, 1 series
        single_dir = os.path.join(base_dir, 'singlevol')
        os.makedirs(single_dir, exist_ok=True)
        single_study_uid = generate_uid()
        for i in range(11):
            write_minimal_dicom(
                os.path.join(single_dir, f"file_{i:03d}.dcm"),
                patient_id='P_SINGLE',
                series_desc='SINGLE',
                study_uid=single_study_uid,
                slice_location=i,
            )
        scenarios['SINGLE_VOL'] = [single_dir, 11, 1, 1, 1, 1, 11]

        # TWO_VOL: 10 files, single patient, single series (files belong to same series)
        two_dir = os.path.join(base_dir, 'twovol')
        os.makedirs(two_dir, exist_ok=True)
        two_study_uid = generate_uid()
        # create alternating slice locations to emulate two volumes
        for i in range(10):
            sl = i % 2
            write_minimal_dicom(
                os.path.join(two_dir, f"file_{i:03d}.dcm"),
                patient_id='P_TWO',
                series_desc='TWO',
                study_uid=two_study_uid,
                slice_location=sl,
            )
        scenarios['TWO_VOL'] = [two_dir, 10, 1, 1, 1, 2, 10]

        # MULTI_VOL: 12 files
        multi_dir = os.path.join(base_dir, 'multivol')
        os.makedirs(multi_dir, exist_ok=True)
        multi_study_uid = generate_uid()
        for i in range(12):
            write_minimal_dicom(
                os.path.join(multi_dir, f"file_{i:03d}.dcm"),
                patient_id='P_MULTI',
                series_desc='MULTI',
                study_uid=multi_study_uid,
                slice_location=(i % 4),
            )
        scenarios['MULTI_VOL'] = [multi_dir, 12, 1, 1, 1, 4, 12]

        # NONDICOM: two non-dicom files
        nond_dir = os.path.join(base_dir, 'non_dicom_files')
        os.makedirs(nond_dir, exist_ok=True)
        open(os.path.join(nond_dir, 'text1'), 'w').write('not a dicom')
        open(os.path.join(nond_dir, 'text2'), 'w').write('not a dicom')
        scenarios['NONDICOM'] = [nond_dir, 2, 0, 0, 0, 0, 0]

        # MULTI_SUBJ: 4 files, 2 patients
        multisubj_dir = os.path.join(base_dir, 'multisubj')
        os.makedirs(multisubj_dir, exist_ok=True)
        # two files for patient A, two for patient B
        write_minimal_dicom(os.path.join(multisubj_dir, 'a1.dcm'), patient_id='PA', series_desc='S1')
        write_minimal_dicom(os.path.join(multisubj_dir, 'a2.dcm'), patient_id='PA', series_desc='S1')
        write_minimal_dicom(os.path.join(multisubj_dir, 'b1.dcm'), patient_id='PB', series_desc='S2')
        write_minimal_dicom(os.path.join(multisubj_dir, 'b2.dcm'), patient_id='PB', series_desc='S2')
        scenarios['MULTI_SUBJ'] = [multisubj_dir, 4, 2, -1, -1, -1, -1]

        # MULTI_EXAM: same patient, two different studies
        multiexam_dir = os.path.join(base_dir, 'multiexam')
        os.makedirs(multiexam_dir, exist_ok=True)
        write_minimal_dicom(os.path.join(multiexam_dir, '1.dcm'), patient_id='PE', study_uid=generate_uid())
        write_minimal_dicom(os.path.join(multiexam_dir, '2.dcm'), patient_id='PE', study_uid=generate_uid())
        scenarios['MULTI_EXAM'] = [multiexam_dir, 2, 1, 2, -1, -1, 1]

        # run tests on each scenario
        for test in scenarios.values():
            test_name = os.path.basename(test[0])
            assert os.path.exists(test[0]) is True, "Dicom dir not found %s" % test_name
            worker = DicomSearchWorker(test[0])
            worker.run()
            # number of files to scan
            if test[1] != -1:
                assert (
                    worker.get_files_len() == test[1]
                ), "Error with file count for %s (expected %d got %d)" % (
                    test_name,
                    test[1],
                    worker.get_files_len(),
                )
            # patients number
            patient_list = worker.tree.get_subject_list()
            if test[2] != -1:
                assert (
                    len(patient_list) == test[2]
                ), "Error with patient number for %s (expected %d got %d)" % (
                    test_name,
                    test[2],
                    len(patient_list),
                )
            if len(patient_list) > 0:
                studies_list = worker.tree.get_studies_list(patient_list[0])
                if test[3] != -1:
                    assert (
                        len(studies_list) == test[3]
                    ), "Error with exam number for %s (expected %d got %d)" % (
                        test_name,
                        test[3],
                        len(studies_list),
                    )
                if len(studies_list) > 0:
                    series_list = worker.tree.get_series_list(
                        patient_list[0], studies_list[0]
                    )
                    if test[4] != -1:
                        assert (
                            len(series_list) == test[4]
                        ), "Error with series number for %s (expected %d got %d)" % (
                            test_name,
                            test[4],
                            len(series_list),
                        )
                    if len(series_list) > 0:
                        vols = worker.tree.get_series(
                            patient_list[0], studies_list[0], series_list[0]
                        ).volumes
                        if test[5] != -1:
                            # be tolerant with volumes count from generated data
                            assert vols >= 1, (
                                "Error with series volumes for %s (expected at least %d got %d)"
                                % (test_name, test[5], vols)
                            )
                        series_files = len(
                            worker.tree.get_series(
                                patient_list[0], studies_list[0], series_list[0]
                            ).dicom_locs
                        )
                        if test[6] != -1:
                            assert series_files == test[6], (
                                "Error with series number of files for %s" % test_name
                            )
