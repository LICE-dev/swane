import os
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian, SecondaryCaptureImageStorage
import tempfile
import datetime
import pytest

from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.tests.helpers.dicom_factory import write_minimal_dicom as _write_minimal_dicom




class TestDicomSearchExtra:
    def test_clean_text_replaces_forbidden_chars(self):
        s = "Hello*World, Test:Name/With|Bad[Chars]"
        out = DicomSearchWorker.clean_text(s)
        assert "*" not in out
        assert "." not in out
        assert "," not in out
        assert "/" not in out
        assert " " not in out
        assert out == out.lower()

    def test_find_series_description_with_description_and_unnamed(self, tmp_path):
        # create two files, one with SeriesDescription, one without
        d1 = tmp_path / "a.dcm"
        d2 = tmp_path / "b.dcm"
        _write_minimal_dicom(str(d1), patient_id="P1", series_desc="MySeries")
        _write_minimal_dicom(str(d2), patient_id="P1")

        # should find the SeriesDescription from the first file
        desc = DicomSearchWorker.find_series_description([str(d1), str(d2)])
        assert desc == "MySeries"

        # if no files have SeriesDescription, return 'Unnamed series'
        d3 = tmp_path / "c.dcm"
        _write_minimal_dicom(str(d3), patient_id="P2")
        desc2 = DicomSearchWorker.find_series_description([str(d3)])
        assert desc2 == "Unnamed series"

    def test_find_series_classification_monkeypatched(self, monkeypatch):
        # monkeypatch extract_metadata and classify_dicom imported in module
        import swane.workers.DicomSearchWorker as dsw

        def fake_extract(ds):
            return {"fake": "meta"}

        def fake_classify(meta):
            return "T1"

        monkeypatch.setattr(dsw, "extract_metadata", fake_extract)
        monkeypatch.setattr(dsw, "classify_dicom", fake_classify)

        # create a dummy dataset object to pass (can be None since extract is patched)
        class Dummy:
            pass

        result = DicomSearchWorker.find_series_classification(Dummy())
        assert result == "T1"

        # if classify_dicom returns 'NOT MR', should return 'Unknown'
        monkeypatch.setattr(dsw, "classify_dicom", lambda meta: "NOT MR")
        result2 = DicomSearchWorker.find_series_classification(Dummy())
        assert result2 == "Unknown"

    def test_run_skips_derived_secondary_and_records_error_message(self, tmp_path):
        # create a dicom with ImageType containing DERIVED and SECONDARY
        d1 = tmp_path / "derived.dcm"
        _write_minimal_dicom(str(d1), patient_id="P_SKIP", image_type=["DERIVED", "SECONDARY"])

        worker = DicomSearchWorker(str(tmp_path), classify=False)
        # ensure unsorted_list points to our file
        worker.unsorted_list = [str(d1)]
        worker.run()

        # the error_message should contain the ImageType tuple/list
        assert any(
            (isinstance(m, (list, tuple)) and "DERIVED" in m and "SECONDARY" in m) or (m == ["DERIVED", "SECONDARY"]) for m in worker.error_message
        )

    def test_multiframe_and_enhanced_and_mosaic_cases(self, tmp_path):
        # multiframe: NumberOfFrames > 1
        mf = tmp_path / "multiframe.dcm"
        _write_minimal_dicom(str(mf), patient_id="P_MF", number_of_frames=5)

        # enhanced/mosaic are complex vendors formats; create representative ImageType values
        enh = tmp_path / "enhanced.dcm"
        _write_minimal_dicom(str(enh), patient_id="P_ENH", image_type=["ORIGINAL", "PRIMARY", "ASL"])  # treated as ASL

        mosaic = tmp_path / "mosaic.dcm"
        _write_minimal_dicom(str(mosaic), patient_id="P_MOS", image_type=["PROJECTION IMAGE"])  # treated as projection

        # run worker on all files
        worker = DicomSearchWorker(str(tmp_path), classify=False)
        worker.unsorted_list = [str(mf), str(enh), str(mosaic)]
        worker.run()

        # multiframe should be stored as multi_frame_series in the series (in add_dicom_loc call)
        # verify tree has subject P_MF
        subjects = worker.tree.get_subject_list()
        assert "P_MF" in subjects
        # ensure enhanced and mosaic image types produced error messages recorded
        assert any("ASL" in str(m) or "PROJECTION IMAGE" in str(m) for m in worker.error_message)
