"""Unit tests for :mod:`swane.utils.SubjectInputStateList`."""

import os

from swane.utils.SubjectInputStateList import SubjectInputStateList, SubjectInputState
from swane.utils.DataInputList import DataInputList


def test_default_state():
    state = SubjectInputState()
    assert state.loaded is False
    assert state.volumes == 0


def test_mandatory_inputs_present_optional_skipped(global_config):
    input_list = SubjectInputStateList("/dicom", global_config)

    # T13D is mandatory and always present
    assert DataInputList.T13D in input_list
    assert input_list.is_ref_loaded() is False

    # a disabled optional series is not added
    assert DataInputList.FLAIR2D_TRA not in input_list

    assert input_list.get_dicom_dir(DataInputList.T13D) == os.path.join(
        "/dicom", str(DataInputList.T13D)
    )


def test_optional_series_included_when_enabled(global_config):
    global_config["optional_series"]["fmri_0"] = "true"
    input_list = SubjectInputStateList("/dicom", global_config)
    assert DataInputList["FMRI_0"] in input_list


def test_is_ref_loaded_tracks_t13d(global_config):
    input_list = SubjectInputStateList("/dicom", global_config)
    input_list[DataInputList.T13D].loaded = True
    assert input_list.is_ref_loaded() is True
