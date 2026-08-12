import os
import tempfile
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.tests.helpers.dicom_factory import write_minimal_dicom
import swane.workers.DicomSearchWorker as dsmod


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
    # monkeypatch the imported classifier functions in module namespace
    monkeypatch.setattr(dsmod, 'extract_metadata', lambda ds: {'dummy': True})
    monkeypatch.setattr(dsmod, 'classify_dicom', lambda meta: 'MYCLASS')
    class FakeDS:
        pass

    assert DicomSearchWorker.find_series_classification(FakeDS()) == 'MYCLASS'

    # simulate NOT MR
    monkeypatch.setattr(dsmod, 'classify_dicom', lambda meta: 'NOT MR')
    assert DicomSearchWorker.find_series_classification(FakeDS()) == 'Unknown'
