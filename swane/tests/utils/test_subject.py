import os
import tempfile
from swane.utils.Subject import Subject, SubjectRet
from swane.utils.DataInputList import DataInputList


class FakeConfig:
    def __init__(self, main_dir, default_dicom='dicom'):
        self._main = main_dir
        self._default = default_dicom

    def get_main_working_directory(self):
        return self._main

    def get_default_dicom_folder(self):
        return self._default


class FakeDep:
    def __init__(self):
        pass


def test_check_subject_folder_and_dicom_count(tmp_path):
    main = tmp_path / 'main'
    main.mkdir()
    subj = main / 'subj1'
    subj.mkdir()
    dicom_dir = subj / 'dicom'
    dicom_dir.mkdir()
    # create subfolders for each DataInputList
    for di in DataInputList:
        p = dicom_dir / str(di)
        p.mkdir()
        # create a dummy file in one
        if di == list(DataInputList)[0]:
            f = p / 'f.dcm'
            f.write_text('x')

    cfg = FakeConfig(str(main))
    s = Subject(cfg, FakeDep())
    # non existing path
    assert s.check_subject_folder(str(subj / 'no')) == SubjectRet.FolderNotFound
    # space in path
    badpath = tmp_path / 'bad path'
    badpath.mkdir()
    assert s.check_subject_folder(str(badpath)) == SubjectRet.PathBlankSpaces

    # outside main
    other = tmp_path / 'other'
    other.mkdir()
    assert s.check_subject_folder(str(other)) == SubjectRet.FolderOutsideMain

    # valid
    assert s.check_subject_folder(str(subj)) == SubjectRet.ValidFolder
    s.folder = str(subj)
    s.global_config = cfg
    # count files in dicom folder for first DataInputList
    di0 = list(DataInputList)[0]
    assert s.dicom_folder_count(di0) >= 0

