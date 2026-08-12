import os
import tempfile
import sys
import types
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.tests.helpers.dicom_factory import write_minimal_dicom
import swane.workers.DicomSearchWorker as dsmod


def _monkeypatch_dicom_sequence_classifier(monkeypatch, classify_value):
    fake_module = types.ModuleType("dicom_sequence_classifier")
    fake_module.extract_metadata = lambda ds: {"dummy": True}
    fake_module.classify_dicom = lambda meta: classify_value
    monkeypatch.setitem(sys.modules, "dicom_sequence_classifier", fake_module)


def test_clean_text():
    s = 'Series:Name/With*Chars'
    cleaned = DicomSearchWorker.clean_text(s)
    assert ' ' not in cleaned
    assert ':' not in cleaned
    assert cleaned == 'series_name_with_chars'


def test_find_series_description(tmp_path):
    d = tmp_path / 'dicom'
    d.mkdir()
    f1 = str(d / 'f1.dcm')
    f2 = str(d / 'f2.dcm')
    write_minimal_dicom(f1, series_desc=None)
    write_minimal_dicom(f2, series_desc='MySeries')
    res = DicomSearchWorker.find_series_description([f1, f2])
    assert res == 'MySeries'


def test_find_series_classification(monkeypatch):
    _monkeypatch_dicom_sequence_classifier(monkeypatch, 'MYCLASS')

    class FakeDS:
        pass

    assert DicomSearchWorker.find_series_classification(FakeDS()) == 'MYCLASS'

    # simulate NOT MR
    _monkeypatch_dicom_sequence_classifier(monkeypatch, 'NOT MR')
    assert DicomSearchWorker.find_series_classification(FakeDS()) == 'Unknown'
