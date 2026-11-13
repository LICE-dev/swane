"""Tests for the temporary test-only FSL policy override.

TEMPORARY: remove with ``swane/tests/helpers/fsl_policy_override.py``.
"""

import pytest

from swane.config import dependency_policy, preference_list
from swane.config.config_enums import GlobalPrefCategoryList
from swane.config.dependency_policy import default_engines
from swane.tests.helpers import fsl_policy_override


@pytest.fixture
def restore_policy(monkeypatch):
    """Let monkeypatch undo whatever the override changes."""
    synth = preference_list.GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
    monkeypatch.setattr(preference_list, "DEFAULT_ENGINES", dict(default_engines(True)))
    for key, engine in default_engines(True).items():
        monkeypatch.setattr(synth[key], "default", engine)
    return synth


@pytest.mark.parametrize("value", [None, "", "1", "false"])
def test_override_is_off_unless_variable_is_zero(monkeypatch, restore_policy, value):
    if value is None:
        monkeypatch.delenv(fsl_policy_override.ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(fsl_policy_override.ENV_VAR, value)

    assert fsl_policy_override.apply_fsl_policy_override() is False
    assert dependency_policy.FSL_MANDATORY is True
    for key, engine in default_engines(True).items():
        assert preference_list.DEFAULT_ENGINES[key] == engine
        assert restore_policy[key].default == engine


def test_override_switches_constant_and_import_time_defaults(
    monkeypatch, restore_policy
):
    monkeypatch.setenv(fsl_policy_override.ENV_VAR, "0")
    defaults = preference_list.DEFAULT_ENGINES

    assert fsl_policy_override.apply_fsl_policy_override() is True
    assert dependency_policy.FSL_MANDATORY is False
    # Updated in place: holders of the dict see the FSL-free engines too.
    assert preference_list.DEFAULT_ENGINES is defaults
    for key, engine in default_engines(False).items():
        assert defaults[key] == engine
        assert restore_policy[key].default == engine
