import pytest

from swane.config.config_enums import GlobalPrefCategoryList, TractographyEngine
from swane.config.preference_list import GLOBAL_PREFERENCES, WF_PREFERENCES, TRACTS
from swane.utils.DataInputList import DataInputList
from swane.utils.qt_compat import QT_AVAILABLE

FSL_ONLY_TRACT_KEYS = {"atr", "str", "cbd", "cbp", "cbt"}
FSL_ONLY_KEYS = FSL_ONLY_TRACT_KEYS | {
    "tractography_threshold",
    "track_procs",
    "old_eddy_correct",
}
DIPY_ONLY_KEYS = {"cingulum", "seed_density", "max_angle", "step_size"}
# Every locally-available tract checkbox not gated to FSL, plus the master
# "tractography" toggle: these stay active on both engines (spec section 2).
ENGINE_NEUTRAL_KEYS = {"tractography"} | (set(TRACTS.keys()) - FSL_ONLY_TRACT_KEYS)


def test_engine_enum_values():
    assert TractographyEngine.FSL_XTRACT.value == "FSL (XTRACT/probtrackx2)"
    assert TractographyEngine.DIPY_RECOBUNDLES.value == "dipy (CSD + RecoBundles)"


def test_engine_pref_default_and_dependency():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["tractography_engine"]
    assert entry.default == TractographyEngine.DIPY_RECOBUNDLES
    assert entry.option_dependency[TractographyEngine.DIPY_RECOBUNDLES][0] == "is_dipy"
    # FSL_XTRACT has no dependency clause: FSL is the pre-existing global requirement
    assert TractographyEngine.FSL_XTRACT not in entry.option_dependency


def test_new_dipy_prefs_exist():
    dti = WF_PREFERENCES[DataInputList.DTI]
    for key in ("cingulum", "seed_density", "max_angle", "step_size"):
        assert key in dti


def test_new_dipy_prefs_types_and_defaults():
    dti = WF_PREFERENCES[DataInputList.DTI]
    from swane.config.config_enums import InputTypes

    assert dti["cingulum"].input_type == InputTypes.BOOLEAN
    assert dti["cingulum"].default == "false"

    assert dti["seed_density"].input_type == InputTypes.INT
    assert dti["seed_density"].default == 2

    assert dti["max_angle"].input_type == InputTypes.FLOAT
    assert dti["max_angle"].default == 20.0

    assert dti["step_size"].input_type == InputTypes.FLOAT
    assert dti["step_size"].default == 0.2


def test_old_eddy_correct_contract_unchanged():
    entry = WF_PREFERENCES[DataInputList.DTI]["old_eddy_correct"]
    assert entry.default == "false"
    assert entry.label == "Use older but faster fsl eddy_correct"
    req = entry.pref_requirement[GlobalPrefCategoryList.SYNTH]
    assert ("tractography_engine", TractographyEngine.FSL_XTRACT) in req
    assert entry.pref_requirement_fail_tooltip == "dipy always uses nlmeans"


def test_fsl_only_keys_require_fsl_engine():
    dti = WF_PREFERENCES[DataInputList.DTI]
    for key in FSL_ONLY_KEYS:
        req = dti[key].pref_requirement[GlobalPrefCategoryList.SYNTH]
        assert ("tractography_engine", TractographyEngine.FSL_XTRACT) in req, key


def test_dipy_only_keys_require_dipy_engine():
    dti = WF_PREFERENCES[DataInputList.DTI]
    for key in DIPY_ONLY_KEYS:
        req = dti[key].pref_requirement[GlobalPrefCategoryList.SYNTH]
        assert ("tractography_engine", TractographyEngine.DIPY_RECOBUNDLES) in req, key


def test_engine_neutral_keys_have_no_engine_requirement():
    dti = WF_PREFERENCES[DataInputList.DTI]
    for key in ENGINE_NEUTRAL_KEYS:
        req = dti[key].pref_requirement
        if req is not None and GlobalPrefCategoryList.SYNTH in req:
            for pair in req[GlobalPrefCategoryList.SYNTH]:
                assert pair[0] != "tractography_engine", key


if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — live gating evaluator tests skipped",
        allow_module_level=True,
    )

from swane.ui.PreferencesWindow import PreferencesWindow


class TestLiveGatingEvaluator:
    """Drive the real PreferencesWindow gating evaluator (requirement_changed),
    the same mechanism proven for deskull_engine/registration engine, rather
    than re-implementing the pref_requirement resolution logic in the test.
    """

    ALL_KEYS = FSL_ONLY_KEYS | DIPY_ONLY_KEYS | ENGINE_NEUTRAL_KEYS

    def _build_window(self, global_config, dependency_manager, engine):
        global_config[GlobalPrefCategoryList.SYNTH]["tractography_engine"] = engine.name
        window = PreferencesWindow(global_config, dependency_manager, is_workflow=True)
        return window

    def _enabled(self, window, key):
        x = window.input_keys[DataInputList.DTI][key]
        return window.inputs[x].input_field.isEnabled()

    def test_dipy_engine_greys_fsl_only_and_activates_dipy_only(
        self, qtbot, global_config, dependency_manager
    ):
        window = self._build_window(
            global_config, dependency_manager, TractographyEngine.DIPY_RECOBUNDLES
        )
        qtbot.addWidget(window)

        for key in FSL_ONLY_KEYS:
            assert self._enabled(window, key) is False, key
        for key in DIPY_ONLY_KEYS:
            assert self._enabled(window, key) is True, key
        for key in ENGINE_NEUTRAL_KEYS:
            assert self._enabled(window, key) is True, key

    def test_fsl_engine_greys_dipy_only_and_activates_fsl_only(
        self, qtbot, global_config, dependency_manager
    ):
        window = self._build_window(
            global_config, dependency_manager, TractographyEngine.FSL_XTRACT
        )
        qtbot.addWidget(window)

        for key in FSL_ONLY_KEYS:
            assert self._enabled(window, key) is True, key
        for key in DIPY_ONLY_KEYS:
            assert self._enabled(window, key) is False, key
        for key in ENGINE_NEUTRAL_KEYS:
            assert self._enabled(window, key) is True, key
