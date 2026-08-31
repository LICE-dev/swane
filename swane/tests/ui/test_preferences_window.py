"""Head-less tests for :class:`swane.ui.PreferencesWindow`."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine
from swane.ui.PreferencesWindow import PreferencesWindow


class TestRegistrationEngineCombo:
    """Regression coverage for the "Registration engine" combo in Global
    settings: an option gated by an external-tool dependency (antspyx for
    ANTS) must never appear selectable, nor silently overwrite a saved value,
    when that dependency is unmet.
    """

    def _engine_combo(self, window):
        x = window.input_keys[GlobalPrefCategoryList.SYNTH]["engine"]
        return window.inputs[x], window.inputs[x].input_field

    def test_without_antspyx_ants_option_stays_disabled_across_reopens(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        monkeypatch.setattr(dependency_manager, "is_antspyx", lambda: False)

        for _ in range(3):
            window = PreferencesWindow(global_config, dependency_manager, False)
            qtbot.addWidget(window)
            entry, combo = self._engine_combo(window)
            ants_index = combo.findData(RegistrationEngine.ANTS)

            assert combo.model().item(ants_index).isEnabled() is False
            assert combo.itemData(combo.currentIndex()) == RegistrationEngine.FSL

            window.save_preferences()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.FSL
        )

    def test_with_antspyx_selecting_ants_persists_across_reopen(
        self, qtbot, global_config, dependency_manager
    ):
        assert dependency_manager.is_antspyx() is True

        window1 = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window1)
        entry1, combo1 = self._engine_combo(window1)
        ants_index = combo1.findData(RegistrationEngine.ANTS)

        assert combo1.model().item(ants_index).isEnabled() is True
        combo1.setCurrentIndex(ants_index)
        window1.save_preferences()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.ANTS
        )

        window2 = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window2)
        _, combo2 = self._engine_combo(window2)

        assert combo2.itemData(combo2.currentIndex()) == RegistrationEngine.ANTS
