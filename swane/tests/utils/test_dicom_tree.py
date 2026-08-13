"""Unit tests for :mod:`swane.utils.DicomTree` (DicomSeries / DicomTree)."""

import pytest

from swane.utils.DicomTree import DicomTree, DicomSeries
from swane.tests.helpers.dicom_factory import write_minimal_dicom


class TestDicomSeries:

    def test_volume_and_frame_counting(self):
        series = DicomSeries()
        series.add_dicom_loc("a", False, 0.0, "uid_a")  # first position
        series.add_dicom_loc("b", False, 1.0, "uid_b")
        series.add_dicom_loc("c", False, 0.0, "uid_c")  # repeats first position
        assert series.frames == 3
        assert series.volumes == 2
        assert len(series.dicom_locs) == 3

    def test_dedup_by_sop_uid_and_location(self):
        series = DicomSeries()
        series.add_dicom_loc("a", False, 0.0, "uid_a")
        # same SOPInstanceUID -> ignored
        series.add_dicom_loc("b", False, 2.0, "uid_a")
        # same file location -> ignored
        series.add_dicom_loc("a", False, 5.0, "uid_z")
        assert series.dicom_locs == ["a"]

    def test_refine_frame_number_zeroes_small_non_mosaic(self, tmp_path):
        path = write_minimal_dicom(str(tmp_path / "f.dcm"))
        series = DicomSeries()
        series.add_dicom_loc(path, False, 0.0, "u1")
        series.frames = 5  # fewer than 10 and not a mosaic
        series.refine_frame_number()
        assert series.frames == 0

    def test_refine_frame_number_keeps_mosaic(self, tmp_path):
        path = write_minimal_dicom(
            str(tmp_path / "m.dcm"), image_type=["ORIGINAL", "PRIMARY", "MOSAIC"]
        )
        series = DicomSeries()
        series.add_dicom_loc(path, False, 0.0, "u1")
        series.frames = 5
        series.refine_frame_number()
        assert series.frames == 5


class TestDicomTree:

    def test_build_and_query(self):
        tree = DicomTree("/some/dir")
        tree.add_subject("S1", "Name^One")
        tree.add_study("S1", "study1")
        series = tree.add_series("S1", "study1", 3)

        assert isinstance(series, DicomSeries)
        assert tree.get_subject_list() == ["S1"]
        assert tree.get_studies_list("S1") == ["study1"]
        assert tree.get_series_list("S1", "study1") == [3]
        assert tree.get_series("S1", "study1", 3) is series

    def test_queries_on_unknown_keys(self):
        tree = DicomTree("/some/dir")
        assert tree.get_studies_list("nope") == []
        assert tree.get_series_list("nope", "x") == []
        assert tree.get_series("nope", "x", 1) is None

    def test_add_on_missing_parents_raises(self):
        tree = DicomTree("/some/dir")
        with pytest.raises(Exception):
            tree.add_study("missing", "study")
        with pytest.raises(Exception):
            tree.add_series("missing", "study", 1)

        tree.add_subject("S2", "n")
        with pytest.raises(Exception):
            tree.add_series("S2", "no_such_study", 1)
