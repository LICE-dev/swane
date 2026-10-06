"""``MainWorkflow.set_analyses_request`` decides whether the reference
workflow builds the shared tissue segmentation: only when FLAT1, dipy
tractography or the NILEARN resting state will consume it.

Only the request gate is exercised (on a bare ``MainWorkflow`` instance); no
graph is built and no external tool runs.
"""

from unittest.mock import MagicMock

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
from swane.utils.DataInputList import DataInputList as DIL
from swane.utils.DependencyManager import DependencyManager
from swane.utils.SubjectInputStateList import (
    SubjectInputState,
    SubjectInputStateList,
)


@pytest.fixture
def request_gate(subject_config, global_config, tmp_path, monkeypatch):
    # both fMRI engines available, so resolve_fmri_engine honours the setting
    monkeypatch.setattr(DependencyManager, "is_nilearn", staticmethod(lambda: True))
    monkeypatch.setattr(DependencyManager, "is_fsl", staticmethod(lambda: True))

    def _gate(
        flat1=False,
        flair3d=False,
        dti=False,
        tractography=False,
        tractography_engine="FSL_XTRACT",
        fmri_rs=False,
        fmri_engine="FSL",
    ):
        inputs = SubjectInputStateList(str(tmp_path), global_config)
        for data_input in (DIL.FLAIR3D, DIL.DTI, DIL.FMRI_RS):
            inputs.setdefault(data_input, SubjectInputState())
        inputs[DIL.T13D].loaded = True
        inputs[DIL.FLAIR3D].loaded = flair3d
        inputs[DIL.DTI].loaded = dti
        inputs[DIL.FMRI_RS].loaded = fmri_rs

        subject_config[DIL.T13D]["flat1"] = "true" if flat1 else "false"
        subject_config[DIL.DTI]["tractography"] = "true" if tractography else "false"
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["tractography_engine"] = tractography_engine
        synth["fmri_engine"] = fmri_engine

        dependency_manager = MagicMock()
        dependency_manager.is_freesurfer.return_value = False
        dependency_manager.is_slicer.return_value = False

        main = MainWorkflow.__new__(MainWorkflow)
        main.global_config = global_config
        main.subject_config = subject_config
        main.dependency_manager = dependency_manager
        main.subject_input_state_list = inputs
        main.set_analyses_request()
        return main.is_tissue_segmentation

    return _gate


def test_nothing_requested(request_gate):
    assert request_gate() is False


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        # FLAT1 needs both the preference and a loaded FLAIR3D
        ({"flat1": True, "flair3d": True}, True),
        ({"flat1": True, "flair3d": False}, False),
        ({"flat1": False, "flair3d": True}, False),
    ],
)
def test_flat1(request_gate, kwargs, expected):
    assert request_gate(**kwargs) is expected


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        (
            {
                "dti": True,
                "tractography": True,
                "tractography_engine": "DIPY_RECOBUNDLES",
            },
            True,
        ),
        # FSL XTRACT tractography does not use the tissue maps
        (
            {"dti": True, "tractography": True, "tractography_engine": "FSL_XTRACT"},
            False,
        ),
        # dipy preprocessing without tractography does not use them either
        (
            {
                "dti": True,
                "tractography": False,
                "tractography_engine": "DIPY_RECOBUNDLES",
            },
            False,
        ),
        # no DTI series
        (
            {
                "dti": False,
                "tractography": True,
                "tractography_engine": "DIPY_RECOBUNDLES",
            },
            False,
        ),
    ],
)
def test_dipy_tractography(request_gate, kwargs, expected):
    assert request_gate(**kwargs) is expected


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"fmri_rs": True, "fmri_engine": "NILEARN"}, True),
        ({"fmri_rs": True, "fmri_engine": "FSL"}, False),
        ({"fmri_rs": False, "fmri_engine": "NILEARN"}, False),
    ],
)
def test_resting_state(request_gate, kwargs, expected):
    assert request_gate(**kwargs) is expected
