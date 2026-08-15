"""Unit tests for :class:`swane.utils.Subject.Subject`.

Consolidates the former top-level ``test_4_subject`` (full import lifecycle,
now fed by phantom DICOMs) and the lightweight folder-validation checks.
"""

import os
from types import SimpleNamespace

import swane.utils.Subject as subject_module
from swane.utils.DicomTree import DicomTree
from swane.utils.Subject import Subject, SubjectRet
from swane.utils.DataInputList import DataInputList


def _scan_first_series(dicom_path):
    """Return the first DicomSeries found under ``dicom_path``."""
    from swane.workers.DicomSearchWorker import DicomSearchWorker

    worker = DicomSearchWorker(dicom_path)
    worker.run()
    subject = worker.tree.get_subject_list()[0]
    study = worker.tree.get_studies_list(subject)[0]
    series_id = worker.tree.get_series_list(subject, study)[0]
    return worker.tree.get_series(subject, study, series_id)


class TestSubjectFolders:
    """Folder creation / validation, no DICOM import."""

    def test_create_new_subject_dir_validation(self, global_config, dependency_manager):
        subject = Subject(global_config, dependency_manager)
        assert (
            subject.create_new_subject_dir("Invalid with space")
            == SubjectRet.PathBlankSpaces
        )
        assert (
            subject.create_new_subject_dir("Invalid*char") == SubjectRet.PathBlankSpaces
        )
        assert subject.create_new_subject_dir(None) == SubjectRet.FolderNotFound
        assert subject.create_new_subject_dir("") == SubjectRet.FolderNotFound
        assert subject.create_new_subject_dir("subj_01") == SubjectRet.ValidFolder
        assert (
            subject.create_new_subject_dir("subj_01") == SubjectRet.FolderAlreadyExists
        )

    def test_check_and_fix_subject_folder(self, global_config, dependency_manager):
        main = global_config.get_main_working_directory()
        subject = Subject(global_config, dependency_manager)

        # a valid subject to compare against
        assert subject.create_new_subject_dir("subj_ok") == SubjectRet.ValidFolder
        valid_folder = subject.folder

        checker = Subject(global_config, dependency_manager)
        assert (
            checker.check_subject_folder(os.path.join(main, "missing"))
            == SubjectRet.FolderNotFound
        )

        space_folder = os.path.join(main, "sub space")
        os.makedirs(space_folder)
        assert checker.check_subject_folder(space_folder) == SubjectRet.PathBlankSpaces

        assert (
            checker.check_subject_folder(os.path.expanduser("~"))
            == SubjectRet.FolderOutsideMain
        )

        no_subtree = os.path.join(main, "no_subtree")
        os.makedirs(no_subtree)
        assert checker.check_subject_folder(no_subtree) == SubjectRet.InvalidFolderTree

        assert checker.check_subject_folder(valid_folder) == SubjectRet.ValidFolder

        # fix_subject_folder_subtree turns an invalid folder into a valid one
        checker.fix_subject_folder_subtree(no_subtree)
        assert checker.check_subject_folder(no_subtree) == SubjectRet.ValidFolder

    def test_subject_config_error_is_not_reported_as_missing_folder(
        self, global_config, dependency_manager, monkeypatch
    ):
        class FailingConfigManager:
            def __init__(self, *args, **kwargs):
                raise OSError("configuration unavailable")

        monkeypatch.setattr(subject_module, "ConfigManager", FailingConfigManager)
        subject = Subject(global_config, dependency_manager)

        assert (
            subject.create_new_subject_dir("subj_config_error")
            == SubjectRet.ConfigError
        )


class TestSubjectWorkflowControl:
    def test_stop_workflow_returns_stopped_and_sets_event(
        self, global_config, dependency_manager
    ):
        subject = Subject(global_config, dependency_manager)
        stop_event = SimpleNamespace(set_called=False)
        stop_event.set = lambda: setattr(stop_event, "set_called", True)
        subject.workflow_process = SimpleNamespace(stop_event=stop_event)
        subject.is_workflow_process_alive = lambda: True

        assert subject.stop_workflow() == SubjectRet.ExecWfStopped
        assert stop_event.set_called is True

    def test_stop_workflow_reports_when_process_is_not_running(
        self, global_config, dependency_manager
    ):
        subject = Subject(global_config, dependency_manager)
        subject.is_workflow_process_alive = lambda: False

        assert subject.stop_workflow() == SubjectRet.ExecWfStatusError


class TestSubjectDicomChecks:
    def test_check_input_folder_step3_accepts_no_status_callback(
        self, global_config, dependency_manager
    ):
        subject = Subject(global_config, dependency_manager)
        assert (
            subject.create_new_subject_dir("subj_no_callback") == SubjectRet.ValidFolder
        )
        worker = SimpleNamespace(
            tree=DicomTree(subject.dicom_folder(DataInputList.T13D))
        )

        subject.check_input_folder_step3(DataInputList.T13D, worker)

    def test_check_input_folder_step3_reports_when_series_vanishes(
        self, global_config, dependency_manager
    ):
        # Simulates a tree that agrees there is exactly one subject/study/series
        # but whose get_series lookup no longer finds it (e.g. a race with a
        # concurrent tree mutation). Must not hang the UI in the loading state.
        subject = Subject(global_config, dependency_manager)
        assert (
            subject.create_new_subject_dir("subj_vanishing_series")
            == SubjectRet.ValidFolder
        )

        fake_tree = SimpleNamespace(
            get_subject_list=lambda: ["S1"],
            get_studies_list=lambda subj: ["study1"],
            get_series_list=lambda subj, study: [1],
            get_series=lambda subj, study, series: None,
        )
        worker = SimpleNamespace(tree=fake_tree, dicom_dir="/some/dir")

        calls = []
        subject.check_input_folder_step3(
            DataInputList.T13D,
            worker,
            status_callback=lambda *args: calls.append(args),
        )

        assert calls == [
            (DataInputList.T13D, SubjectRet.DataInputWarningNoDicom, worker)
        ]
        assert subject.input_state_list[DataInputList.T13D].loaded is False


class TestSubjectDicomImport:
    """Full DICOM import lifecycle driven by phantom series."""

    def test_import_checks_and_clear(
        self, global_config, dependency_manager, phantom_dicom_tree, qtbot
    ):
        # FMRI_0 is optional: enable it so it appears in the input state list.
        global_config["optional_series"]["fmri_0"] = "true"

        subject = Subject(global_config, dependency_manager)
        assert subject.create_new_subject_dir("subj_01") == SubjectRet.ValidFolder

        single = _scan_first_series(phantom_dicom_tree["SINGLE_VOL"].path)

        # valid import
        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList.T13D,
                copy_list=single.dicom_locs,
                vols=single.volumes,
                mod=single.modality,
                force_modality=False,
            )
            == SubjectRet.DataImportCompleted
        )

        # importing again into a loaded slot is refused
        subject.input_state_list[DataInputList.T13D].loaded = True
        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList.T13D,
                copy_list=single.dicom_locs,
                vols=single.volumes,
                mod=single.modality,
                force_modality=False,
            )
            == SubjectRet.DataInputNonEmpty
        )

        assert subject.dicom_folder_count(DataInputList.T13D) == len(single.dicom_locs)

        # min-volumes check (fMRI needs >= 4 volumes, single has 1)
        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList["FMRI_0"],
                copy_list=single.dicom_locs,
                vols=single.volumes,
                mod=single.modality,
                force_modality=False,
            )
            == SubjectRet.DataImportErrorVolumesMin
        )

        # wrong modality without force
        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList.FLAIR3D,
                copy_list=single.dicom_locs,
                vols=single.volumes,
                mod="pt",
                force_modality=False,
            )
            == SubjectRet.DataImportErrorModality
        )

        # wrong modality forced through
        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList.FLAIR3D,
                copy_list=single.dicom_locs,
                vols=single.volumes,
                mod="pt",
                force_modality=True,
            )
            == SubjectRet.DataImportCompleted
        )

        # max-volumes check (FLAIR3D allows 1 volume, multivol has 4)
        multi = _scan_first_series(phantom_dicom_tree["MULTI_VOL"].path)
        subject.clear_import_folder(DataInputList.FLAIR3D)
        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList.FLAIR3D,
                copy_list=multi.dicom_locs,
                vols=multi.volumes,
                mod=multi.modality,
                force_modality=False,
            )
            == SubjectRet.DataImportErrorVolumesMax
        )

        # clear removes the imported files
        assert subject.clear_import_folder(DataInputList.T13D) is True
        assert subject.dicom_folder_count(DataInputList.T13D) == 0

    def test_import_reports_error_when_no_file_actually_copied(
        self, global_config, dependency_manager, phantom_dicom_tree
    ):
        # copy_list pointing at files that no longer exist on disk (e.g. a
        # stale scan) must not be reported as a completed import.
        subject = Subject(global_config, dependency_manager)
        assert (
            subject.create_new_subject_dir("subj_missing_files")
            == SubjectRet.ValidFolder
        )

        single = _scan_first_series(phantom_dicom_tree["SINGLE_VOL"].path)
        missing_locs = [loc + ".does_not_exist" for loc in single.dicom_locs]

        assert (
            subject.dicom_import_to_folder(
                data_input=DataInputList.T13D,
                copy_list=missing_locs,
                vols=single.volumes,
                mod=single.modality,
                force_modality=False,
            )
            == SubjectRet.DataImportErrorCopy
        )
        assert subject.dicom_folder_count(DataInputList.T13D) == 0
