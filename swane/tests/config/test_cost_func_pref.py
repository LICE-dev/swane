import pytest

from swane.config.config_enums import (
    BetweenModFlirtCost,
    GlobalPrefCategoryList,
    RegistrationEngine,
)
from swane.config.preference_list import WF_PREFERENCES
from swane.utils.DataInputList import DataInputList
from swane.utils.qt_compat import QT_AVAILABLE

# Only FLIRT honours cost_func: ANTs maps every option to Mattes MI and
# SynthMorph ignores it, so the preference must be gated to the FSL engine.
COST_FUNC_CATEGORIES = (DataInputList.ASL, DataInputList.PET)


@pytest.mark.parametrize("category", COST_FUNC_CATEGORIES)
def test_cost_func_contract_unchanged(category):
    entry = WF_PREFERENCES[category]["cost_func"]
    assert entry.value_enum is BetweenModFlirtCost
    assert entry.label == "FLIRT between modalities cost function"


def test_cost_func_defaults_unchanged():
    assert (
        WF_PREFERENCES[DataInputList.ASL]["cost_func"].default
        == BetweenModFlirtCost.NORMALIZED_MUTUAL_INFORMATION
    )
    assert (
        WF_PREFERENCES[DataInputList.PET]["cost_func"].default
        == BetweenModFlirtCost.MUTUAL_INFORMATION
    )


@pytest.mark.parametrize("category", COST_FUNC_CATEGORIES)
def test_cost_func_requires_fsl_registration_engine(category):
    entry = WF_PREFERENCES[category]["cost_func"]
    req = entry.pref_requirement[GlobalPrefCategoryList.SYNTH]
    assert req == [("engine", RegistrationEngine.FSL)]
    assert (
        entry.pref_requirement_fail_tooltip
        == "Only used when the registration engine is FSL"
    )


if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — live gating evaluator tests skipped",
        allow_module_level=True,
    )

from swane.ui.PreferencesWindow import PreferencesWindow


class TestLiveGatingEvaluator:
    """Drive the real PreferencesWindow gating evaluator rather than
    re-implementing the pref_requirement resolution logic in the test.
    """

    def _enabled(self, window, category):
        x = window.input_keys[category]["cost_func"]
        entry = window.inputs[x]
        return entry.input_field.isEnabled() and not entry.input_field.isHidden()

    @pytest.mark.parametrize(
        "engine, expected",
        [
            (RegistrationEngine.FSL, True),
            (RegistrationEngine.ANTS, False),
            (RegistrationEngine.SYNTH, False),
        ],
    )
    def test_cost_func_enabled_only_with_fsl(
        self, qtbot, global_config, dependency_manager, engine, expected
    ):
        global_config[GlobalPrefCategoryList.SYNTH]["engine"] = engine.name
        window = PreferencesWindow(global_config, dependency_manager, is_workflow=True)
        qtbot.addWidget(window)

        for category in COST_FUNC_CATEGORIES:
            assert self._enabled(window, category) is expected, category
