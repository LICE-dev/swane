"""Head-less tests for :class:`swane.ui.PreferenceWizardWindow`."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane.config.config_enums import (
    FreesurferStep,
    GlobalPrefCategoryList,
    RegistrationEngine,
    DeskullEngine,
)
from swane.utils.DataInputList import DataInputList
from swane.utils.ResourceManager import ResourceManager
from swane.ui.PreferenceWizardWindow import PreferenceWizardWindow, UserPreferences


class TestPreferenceWizard:

    def test_build(self, qtbot, global_config, dependency_manager):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert wizard.windowTitle() != ""
        assert isinstance(wizard.user_prefs, UserPreferences)
        assert wizard._stack.count() >= 1

    def test_navigation_next_then_back(self, qtbot, global_config, dependency_manager):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        start = wizard._stack.currentIndex()
        wizard._go_next()
        assert wizard._stack.currentIndex() >= start
        wizard._go_back()
        assert wizard._stack.currentIndex() == start

    def test_cortical_parcellation_checkbox_updates_preferences(
        self, qtbot, global_config, dependency_manager
    ):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        page = wizard._page_freesurfer_outputs()
        qtbot.addWidget(page)

        wizard._cb_freesurfer_cortical_parcellation.setChecked(True)

        assert wizard.user_prefs.cortical_parcellation_enabled is True

    def test_synthseg_requires_advanced_models_and_sufficient_ram(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        monkeypatch.setattr(
            global_config, "apply_resource_profile", lambda profile: None
        )
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: True)
        monkeypatch.setattr(
            ResourceManager, "synth_seg_ram_requirements", staticmethod(lambda: 10)
        )
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "9"
        wizard.user_prefs.cortical_parcellation_enabled = True
        wizard.user_prefs.use_advanced_models = True

        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.AUTORECON_PIAL
        )

        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "10"
        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.SYNTHSEG
        )


class TestPreferenceWizardRegistrationEngine:
    """D2: the wizard writes the ``engine`` preference instead of ``morph``.

    ANTs is the general default (available whenever antspyx is importable and
    RAM suffices) and does NOT require the advanced-models opt-in. SynthMorph
    stays gated behind that opt-in, like SynthStrip/SynthSeg. FSL is the
    fallback when neither is available/sufficient.
    """

    def _wizard(self, qtbot, global_config, dependency_manager, monkeypatch):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        monkeypatch.setattr(
            global_config, "apply_resource_profile", lambda profile: None
        )
        return wizard

    def test_ants_available_and_sufficient_ram_sets_ants(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspyx", lambda: True)
        monkeypatch.setattr(
            ResourceManager, "ants_ram_requirements", staticmethod(lambda: 8)
        )
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "8"
        wizard.user_prefs.use_advanced_models = False

        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.ANTS
        )

    def test_ants_available_but_insufficient_ram_falls_back(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspyx", lambda: True)
        monkeypatch.setattr(
            ResourceManager, "ants_ram_requirements", staticmethod(lambda: 8)
        )
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: False)
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "4"
        wizard.user_prefs.use_advanced_models = False

        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.FSL
        )

    def test_synth_requires_advanced_models_opt_in_even_if_sufficient_ram(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspyx", lambda: False)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: True)
        monkeypatch.setattr(
            ResourceManager, "synth_morph_ram_requirements", staticmethod(lambda: 8)
        )
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "8"

        wizard.user_prefs.use_advanced_models = False
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.FSL
        )

        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.SYNTH
        )

    def test_neither_available_falls_back_to_fsl(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspyx", lambda: False)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: False)
        wizard.user_prefs.use_advanced_models = True

        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
            == RegistrationEngine.FSL
        )

    def test_morph_key_is_never_written(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: True)
        wizard.user_prefs.use_advanced_models = True

        wizard._apply_settings_config()

        assert "morph" not in global_config[GlobalPrefCategoryList.SYNTH]


class TestPreferenceWizardDeskullEngine:
    """The wizard writes the ``deskull_engine`` preference instead of ``strip``.

    antspynet is the general default (available whenever the antspynet package
    is importable and RAM suffices) and does NOT require the advanced-models
    opt-in. SynthStrip stays gated behind that opt-in, like SynthMorph/SynthSeg.
    FSL BET is the fallback when neither is available/sufficient.
    """

    def _wizard(self, qtbot, global_config, dependency_manager, monkeypatch):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        monkeypatch.setattr(
            global_config, "apply_resource_profile", lambda profile: None
        )
        return wizard

    def test_antspynet_available_and_sufficient_ram_sets_antspynet(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspynet", lambda: True)
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "8"
        wizard.user_prefs.use_advanced_models = False

        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "deskull_engine")
            == DeskullEngine.ANTSPYNET
        )

    def test_synthstrip_requires_advanced_models_opt_in_even_if_sufficient_ram(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspynet", lambda: False)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: True)
        monkeypatch.setattr(
            ResourceManager, "synth_strip_ram_requirements", staticmethod(lambda: 8)
        )
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "8"

        wizard.user_prefs.use_advanced_models = False
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "deskull_engine")
            == DeskullEngine.BET
        )

        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "deskull_engine")
            == DeskullEngine.SYNTHSTRIP
        )

    def test_neither_available_falls_back_to_bet(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspynet", lambda: False)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: False)
        wizard.user_prefs.use_advanced_models = True

        wizard._apply_settings_config()

        assert (
            global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, "deskull_engine")
            == DeskullEngine.BET
        )

    def test_strip_key_is_never_written(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        wizard = self._wizard(qtbot, global_config, dependency_manager, monkeypatch)
        monkeypatch.setattr(dependency_manager, "is_antspynet", lambda: True)
        wizard.user_prefs.use_advanced_models = True

        wizard._apply_settings_config()

        assert "strip" not in global_config[GlobalPrefCategoryList.SYNTH]
