"""Unit tests for :class:`swane.workers.DicomSearchWorker.DicomSearchWorker`.

Consolidates the former ``test_3_dicom_search`` (scenario scan),
``test_3b_dicom_extra`` (edge cases) and the original thin worker test.
"""

import os

import pytest

from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.tests.helpers.dicom_factory import write_minimal_dicom


class TestDicomSearchScenarios:
    """Scan every phantom scenario and check the resulting DicomTree."""

    def test_scan_scenarios(self, phantom_dicom_tree):
        for scenario in phantom_dicom_tree.values():
            assert os.path.exists(scenario.path), (
                "Dicom dir not found %s" % scenario.name
            )
            worker = DicomSearchWorker(scenario.path)
            worker.run()

            if scenario.files != -1:
                assert (
                    worker.get_files_len() == scenario.files
                ), "file count for %s: expected %d got %d" % (
                    scenario.name,
                    scenario.files,
                    worker.get_files_len(),
                )

            subjects = worker.tree.get_subject_list()
            if scenario.subjects != -1:
                assert (
                    len(subjects) == scenario.subjects
                ), "subject count for %s: expected %d got %d" % (
                    scenario.name,
                    scenario.subjects,
                    len(subjects),
                )
            if not subjects:
                continue

            studies = worker.tree.get_studies_list(subjects[0])
            if scenario.studies != -1:
                assert (
                    len(studies) == scenario.studies
                ), "study count for %s: expected %d got %d" % (
                    scenario.name,
                    scenario.studies,
                    len(studies),
                )
            if not studies:
                continue

            series = worker.tree.get_series_list(subjects[0], studies[0])
            if scenario.series != -1:
                assert (
                    len(series) == scenario.series
                ), "series count for %s: expected %d got %d" % (
                    scenario.name,
                    scenario.series,
                    len(series),
                )
            if not series:
                continue

            first = worker.tree.get_series(subjects[0], studies[0], series[0])
            if scenario.volumes != -1:
                assert (
                    first.volumes == scenario.volumes
                ), "volume count for %s: expected %d got %d" % (
                    scenario.name,
                    scenario.volumes,
                    first.volumes,
                )
            if scenario.series_files != -1:
                assert (
                    len(first.dicom_locs) == scenario.series_files
                ), "series file count for %s: expected %d got %d" % (
                    scenario.name,
                    scenario.series_files,
                    len(first.dicom_locs),
                )

    def test_multiframe_volumes(self, phantom_dicom_tree):
        """The multi-frame branch of refine_frame_number is exercised here."""
        scenario = phantom_dicom_tree["MULTIFRAME"]
        worker = DicomSearchWorker(scenario.path)
        worker.run()
        subjects = worker.tree.get_subject_list()
        assert subjects == ["P_MF"]
        studies = worker.tree.get_studies_list(subjects[0])
        series_list = worker.tree.get_series_list(subjects[0], studies[0])
        series = worker.tree.get_series(subjects[0], studies[0], series_list[0])
        assert series.is_multi_frame is True
        assert series.volumes == 2


class TestDicomSearchHelpers:

    def test_clean_text(self):
        cleaned = DicomSearchWorker.clean_text("Series:Name/With*Chars ")
        assert " " not in cleaned
        assert ":" not in cleaned
        assert cleaned == "series_name_with_chars_"
        assert cleaned == cleaned.lower()

    def test_find_series_description(self, tmp_path):
        f1 = str(tmp_path / "f1.dcm")
        f2 = str(tmp_path / "f2.dcm")
        write_minimal_dicom(f1, series_desc=None)
        write_minimal_dicom(f2, series_desc="MySeries")
        assert DicomSearchWorker.find_series_description([f1, f2]) == "MySeries"

    def test_find_series_description_unnamed(self, tmp_path):
        f = str(tmp_path / "f.dcm")
        write_minimal_dicom(f, series_desc=None)
        assert DicomSearchWorker.find_series_description([f]) == "Unnamed series"

    def test_find_series_classification(self, monkeypatch):
        # find_series_classification does a call-time
        # `from dicom_sequence_classifier import extract_metadata, classify_dicom`
        # so we patch the attributes on that module.
        import dicom_sequence_classifier as dsc

        monkeypatch.setattr(dsc, "extract_metadata", lambda ds: {"dummy": True})
        monkeypatch.setattr(dsc, "classify_dicom", lambda meta: "T1")
        assert DicomSearchWorker.find_series_classification(object()) == "T1"

        monkeypatch.setattr(dsc, "classify_dicom", lambda meta: "NOT MR")
        assert DicomSearchWorker.find_series_classification(object()) == "Unknown"


class TestDicomSearchFiltering:
    """ImageType based filtering (reconstructions must be discarded)."""

    def test_derived_secondary_skipped(self, tmp_path):
        write_minimal_dicom(
            str(tmp_path / "derived.dcm"),
            patient_id="P_SKIP",
            image_type=["DERIVED", "SECONDARY"],
        )
        worker = DicomSearchWorker(str(tmp_path))
        worker.run()
        assert worker.tree.get_subject_list() == []
        assert any(
            "DERIVED" in str(m) and "SECONDARY" in str(m) for m in worker.error_message
        )

    def test_asl_and_projection_skipped(self, tmp_path):
        write_minimal_dicom(
            str(tmp_path / "asl.dcm"),
            patient_id="P_ASL",
            image_type=["ORIGINAL", "PRIMARY", "ASL"],
        )
        write_minimal_dicom(
            str(tmp_path / "proj.dcm"),
            patient_id="P_PROJ",
            image_type=["PROJECTION IMAGE"],
        )
        worker = DicomSearchWorker(str(tmp_path))
        worker.run()
        assert worker.tree.get_subject_list() == []
        joined = " ".join(str(m) for m in worker.error_message)
        assert "ASL" in joined
        assert "PROJECTION IMAGE" in joined

    def test_non_dicom_ignored(self, tmp_path):
        (tmp_path / "notes.txt").write_text("not a dicom", encoding="utf-8")
        worker = DicomSearchWorker(str(tmp_path))
        worker.run()
        assert worker.get_files_len() == 1
        assert worker.tree.get_subject_list() == []
