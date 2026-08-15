"""Head-less tests for :class:`swane.ui.PreferenceWizardWindow`."""

from swane.config.config_enums import FreesurferStep, GlobalPrefCategoryList
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
