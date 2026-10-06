"""Tests for the FSL dependency policy (:mod:`swane.config.dependency_policy`)."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from swane.config import dependency_policy
from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import (
    DeskullEngine,
    FmriEngine,
    GlobalPrefCategoryList,
    RegistrationEngine,
    SegmentationEngine,
    TractographyEngine,
)
from swane.config.dependency_policy import default_engines
from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.utils.Subject import Subject

ENGINE_KEYS = (
    "deskull_engine",
    "engine",
    "tractography_engine",
    "segmentation_engine",
    "fmri_engine",
)

FSL_OPTIONS = {
    "deskull_engine": DeskullEngine.BET,
    "engine": RegistrationEngine.FSL,
    "tractography_engine": TractographyEngine.FSL_XTRACT,
    "segmentation_engine": SegmentationEngine.FSL,
    "fmri_engine": FmriEngine.FSL,
}


def test_shipped_policy_makes_fsl_recommended():
    assert dependency_policy.FSL_MANDATORY is False


def test_fsl_mandatory_defaults_to_fsl_engines_except_registration():
    assert default_engines(True) == {
        "deskull_engine": DeskullEngine.BET,
        "engine": RegistrationEngine.ANTS,
        "tractography_engine": TractographyEngine.FSL_XTRACT,
        "segmentation_engine": SegmentationEngine.FSL,
        "fmri_engine": FmriEngine.FSL,
    }


def test_fsl_recommended_defaults_to_fsl_free_engines():
    assert default_engines(False) == {
        "deskull_engine": DeskullEngine.ANTSPYNET,
        "engine": RegistrationEngine.ANTS,
        "tractography_engine": TractographyEngine.DIPY_RECOBUNDLES,
        "segmentation_engine": SegmentationEngine.ANTS,
        "fmri_engine": FmriEngine.NILEARN,
    }


def test_engine_preference_defaults_follow_policy():
    expected = default_engines(dependency_policy.FSL_MANDATORY)
    synth = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]
    for key in ENGINE_KEYS:
        assert synth[key].default == expected[key]


@pytest.mark.parametrize("key", ENGINE_KEYS)
def test_fsl_engine_options_are_gated_on_fsl(key):
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key]
    assert entry.option_dependency[FSL_OPTIONS[key]][0] == "is_fsl"


class _Deps:
    """Every dependency available except, optionally, FSL."""

    def __init__(self, fsl: bool):
        self._fsl = fsl

    def is_fsl(self):
        return self._fsl

    def __getattr__(self, name):
        if name.startswith("is_"):
            return lambda: True
        raise AttributeError(name)


def _set_fsl_engines(config):
    for key, option in FSL_OPTIONS.items():
        config[GlobalPrefCategoryList.SYNTH][key] = option.name


def test_check_dependencies_resets_fsl_engines_without_fsl(tmp_path):
    config = ConfigManager(global_base_folder=str(tmp_path))
    _set_fsl_engines(config)

    config.check_dependencies(_Deps(fsl=False))

    synth = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]
    for key in FSL_OPTIONS:
        assert config[GlobalPrefCategoryList.SYNTH][key] == synth[key].default.name
    # The reset is persisted.
    reloaded = ConfigManager(global_base_folder=str(tmp_path))
    for key in FSL_OPTIONS:
        assert reloaded[GlobalPrefCategoryList.SYNTH][key] == synth[key].default.name


def test_check_dependencies_keeps_fsl_engines_with_fsl(tmp_path):
    config = ConfigManager(global_base_folder=str(tmp_path))
    _set_fsl_engines(config)

    config.check_dependencies(_Deps(fsl=True))

    for key, option in FSL_OPTIONS.items():
        assert config[GlobalPrefCategoryList.SYNTH][key] == option.name


@pytest.mark.parametrize(
    "fsl_mandatory, fsl_installed, expected",
    [
        (True, True, True),
        (True, False, False),
        (False, True, True),
        (False, False, True),
    ],
)
def test_can_generate_workflow_requires_fsl_only_when_mandatory(
    global_config, monkeypatch, fsl_mandatory, fsl_installed, expected
):
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", fsl_mandatory)
    deps = SimpleNamespace(is_fsl=lambda: fsl_installed, is_dcm2niix=lambda: True)
    subject = Subject(global_config, deps)
    subject.input_state_list = SimpleNamespace(is_ref_loaded=lambda: True)

    assert subject.can_generate_workflow() is expected


def test_can_generate_workflow_still_requires_dcm2niix(global_config, monkeypatch):
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
    deps = SimpleNamespace(is_fsl=lambda: True, is_dcm2niix=lambda: False)
    subject = Subject(global_config, deps)
    subject.input_state_list = SimpleNamespace(is_ref_loaded=lambda: True)

    assert subject.can_generate_workflow() is False


def test_dipy_tracts_survive_without_xtract_data(tmp_path):
    """Without FSL's XTRACT data the dipy-supported tracts stay configurable."""
    env = {k: v for k, v in os.environ.items() if k != "FSLDIR"}
    env["HOME"] = str(tmp_path)
    code = (
        "from swane.config.preference_list import TRACTS, XTRACT_DATA_DIR;"
        "assert XTRACT_DATA_DIR == '';"
        "print(' '.join(sorted(TRACTS)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tracts = set(out.split())
    # Default-enabled tracts with a dipy atlas bundle are kept...
    assert {"af", "cst", "or"} <= tracts
    # ...while FSL-only tracts, which need the XTRACT protocols, are dropped.
    assert not tracts & {"ar", "atr", "str", "cbd", "cbp", "cbt"}
