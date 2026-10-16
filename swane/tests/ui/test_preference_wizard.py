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
    PerformanceProfile,
    RegistrationEngine,
    DeskullEngine,
    TractographyEngine,
    SegmentationEngine,
    FmriEngine,
)
from swane.config import dependency_policy
from swane.config.ConfigManager import ConfigManager
from swane.config.preference_list import GLOBAL_PREFERENCES, WF_PREFERENCES
from swane.utils.DataInputList import DataInputList
from swane.utils.ResourceManager import ResourceManager
from swane.ui.PreferenceWizardWindow import (
    PreferenceWizardWindow,
    UserPreferences,
    ENGINE_PREFERENCE_ORDER,
)

DEPENDENCIES = (
    "is_fsl",
    "is_antspyx",
    "is_antspynet",
    "is_dipy",
    "is_nilearn",
    "is_freesurfer_synth",
)


def set_tools(monkeypatch, dependency_manager, *available):
    """Make exactly the named DependencyManager checks report True."""
    for name in DEPENDENCIES:
        monkeypatch.setattr(
            dependency_manager, name, lambda value=name in available: value
        )


def ram_requirement(key, option):
    """RAM requirement the preference metadata declares for an engine option."""
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key]
    for pref, threshold in entry.option_pref_requirement[option][
        GlobalPrefCategoryList.PERFORMANCE
    ]:
        if pref == "ram_gb":
            return threshold


def set_ram(global_config, ram_gb):
    global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = str(ram_gb)


def engine(global_config, key):
    return global_config.getenum_safe(GlobalPrefCategoryList.SYNTH, key)


@pytest.fixture
def wizard(qtbot, global_config, dependency_manager, monkeypatch):
    """A wizard whose profile does not overwrite the RAM set by the test."""
    wizard = PreferenceWizardWindow(global_config, dependency_manager)
    qtbot.addWidget(wizard)
    monkeypatch.setattr(global_config, "apply_resource_profile", lambda profile: None)
    return wizard


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
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth")
        threshold = dict(
            WF_PREFERENCES[DataInputList.T13D][
                "freesurfer_step"
            ].option_pref_requirement[FreesurferStep.SYNTHSEG][
                GlobalPrefCategoryList.PERFORMANCE
            ]
        )["ram_gb"]
        wizard.user_prefs.freesurfer_capable = True
        wizard.user_prefs.cortical_parcellation_enabled = True
        wizard.user_prefs.use_advanced_models = True

        set_ram(global_config, threshold - 1)
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.AUTORECON_PIAL
        )

        set_ram(global_config, threshold)
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.SYNTHSEG
        )

        wizard.user_prefs.use_advanced_models = False
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.AUTORECON_PIAL
        )

    def test_welcome_page_warns_on_windows_only(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        import swane.ui.PreferenceWizardWindow as wizard_module
        from PySide6.QtWidgets import QLabel

        def texts(wizard):
            page = wizard._stack.widget(0)
            return " ".join(label.text() for label in page.findChildren(QLabel))

        monkeypatch.setattr(wizard_module, "is_windows", lambda: True)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert "experimental" in texts(wizard)

        monkeypatch.setattr(wizard_module, "is_windows", lambda: False)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert "experimental" not in texts(wizard)


class TestPreferenceWizardRegistrationEngine:
    """ANTs is the general default and does NOT require the advanced-models
    opt-in. SynthMorph stays gated behind that opt-in. FSL is the fallback
    when it is installed."""

    def test_ants_available_and_sufficient_ram_sets_ants(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_antspyx", "is_fsl")
        set_ram(global_config, ram_requirement("engine", RegistrationEngine.ANTS))
        wizard._apply_settings_config()
        assert engine(global_config, "engine") == RegistrationEngine.ANTS

    def test_synth_requires_advanced_models_opt_in(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth", "is_fsl")
        set_ram(global_config, ram_requirement("engine", RegistrationEngine.SYNTH))

        wizard.user_prefs.use_advanced_models = False
        wizard._apply_settings_config()
        assert engine(global_config, "engine") == RegistrationEngine.FSL

        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert engine(global_config, "engine") == RegistrationEngine.SYNTH

    def test_morph_key_is_never_written(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth")
        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert "morph" not in global_config[GlobalPrefCategoryList.SYNTH]


class TestPreferenceWizardDeskullEngine:
    """antspynet is the general default and does NOT require the advanced-models
    opt-in. SynthStrip stays gated behind that opt-in. FSL BET is the fallback
    when FSL is installed, and the only choice when FSL is mandatory."""

    def test_antspynet_available_and_sufficient_ram_sets_antspynet(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_antspynet", "is_fsl")
        set_ram(
            global_config,
            ram_requirement("deskull_engine", DeskullEngine.ANTSPYNET),
        )
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.ANTSPYNET

    def test_synthstrip_requires_advanced_models_opt_in(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth", "is_fsl")
        set_ram(
            global_config,
            ram_requirement("deskull_engine", DeskullEngine.SYNTHSTRIP),
        )

        wizard.user_prefs.use_advanced_models = False
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.BET

        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.SYNTHSTRIP

    def test_fsl_mandatory_always_sets_bet(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
        set_tools(monkeypatch, dependency_manager, *DEPENDENCIES)
        set_ram(global_config, 64)
        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.BET

    def test_bet_is_not_selected_without_fsl(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        # Nothing is installed: keep the policy default instead of writing an
        # FSL engine the host cannot run, and flag it in the review.
        set_tools(monkeypatch, dependency_manager)
        set_ram(global_config, 64)
        plan = wizard._build_plan(64)
        default = dependency_policy.default_engines(dependency_policy.FSL_MANDATORY)
        assert plan.engines["deskull_engine"] == default["deskull_engine"]
        assert "deskull_engine" in plan.engine_notes

    def test_strip_key_is_never_written(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_antspynet")
        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert "strip" not in global_config[GlobalPrefCategoryList.SYNTH]


class TestPreferenceWizardAnalysisEngines:
    """Tractography, segmentation and task fMRI engines are resolved from the
    installed tools and the profile RAM, like brain extraction and
    registration."""

    @pytest.mark.parametrize(
        "key, python_engine, fsl_engine, python_tool",
        [
            (
                "tractography_engine",
                TractographyEngine.DIPY_RECOBUNDLES,
                TractographyEngine.FSL_XTRACT,
                "is_dipy",
            ),
            (
                "segmentation_engine",
                SegmentationEngine.ANTS,
                SegmentationEngine.FSL,
                "is_antspyx",
            ),
            ("fmri_engine", FmriEngine.NILEARN, FmriEngine.FSL, "is_nilearn"),
        ],
    )
    def test_engine_resolution(
        self,
        wizard,
        global_config,
        dependency_manager,
        monkeypatch,
        key,
        python_engine,
        fsl_engine,
        python_tool,
    ):
        threshold = ram_requirement(key, python_engine)

        # Python engine installed and fits: selected (FSL-optional policy)
        monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
        set_tools(monkeypatch, dependency_manager, python_tool, "is_fsl")
        set_ram(global_config, threshold)
        wizard._apply_settings_config()
        assert engine(global_config, key) == python_engine

        # Python engine does not fit the RAM: FSL takes over
        set_ram(global_config, threshold - 1)
        wizard._apply_settings_config()
        assert engine(global_config, key) == fsl_engine

        # No FSL either: the installed engine is kept and flagged
        set_tools(monkeypatch, dependency_manager, python_tool)
        plan = wizard._build_plan(threshold - 1)
        assert plan.engines[key] == python_engine
        assert key in plan.engine_notes

        # FSL installed but missing the Python tool: FSL
        set_tools(monkeypatch, dependency_manager, "is_fsl")
        wizard._apply_settings_config()
        assert engine(global_config, key) == fsl_engine

        # FSL mandatory: FSL first even when the Python engine fits
        monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
        set_tools(monkeypatch, dependency_manager, python_tool, "is_fsl")
        set_ram(global_config, threshold)
        wizard._apply_settings_config()
        assert engine(global_config, key) == fsl_engine

    def test_every_engine_preference_is_resolved(self):
        engine_keys = {
            key
            for key, entry in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH].items()
            if entry.value_enum is not None and entry.option_dependency
        }
        assert engine_keys == set(ENGINE_PREFERENCE_ORDER)
        for key, order in ENGINE_PREFERENCE_ORDER.items():
            value_enum = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][
                key
            ].value_enum
            assert set(order) == set(value_enum)


class TestPreferenceWizardRerun:
    """Rerunning the wizard turns off what a previous run enabled."""

    def test_synth_reconall_is_reset(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth")
        set_ram(global_config, 64)
        wizard.user_prefs.use_advanced_models = True
        wizard._apply_settings_config()
        assert global_config.getboolean_safe(GlobalPrefCategoryList.SYNTH, "reconall")

        wizard.user_prefs.use_advanced_models = False
        wizard._apply_settings_config()
        assert not global_config.getboolean_safe(
            GlobalPrefCategoryList.SYNTH, "reconall"
        )

    def test_hippocampal_subfields_are_reset(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        wizard.user_prefs.freesurfer_capable = True
        wizard.user_prefs.matlab_capable = True
        wizard.user_prefs.hippocampal_segmentation_enabled = True
        wizard._apply_settings_config()
        assert global_config.getboolean_safe(DataInputList.T13D, "hippo_amyg_labels")
        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.AUTORECON_PIAL
        )

        wizard.user_prefs.hippocampal_segmentation_enabled = False
        wizard._apply_settings_config()
        assert not global_config.getboolean_safe(
            DataInputList.T13D, "hippo_amyg_labels"
        )
        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.DISABLED
        )


class TestPreferenceWizardReview:

    def test_review_matches_applied_settings(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_fsl", "is_antspyx")
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        while not wizard._is_review_page():
            wizard._go_next()
        review = wizard._review_label.text()

        wizard._finish()
        assert wizard._is_applied_page()

        ram_gb = ConfigManager.get_resource_profile_values(PerformanceProfile.BALANCED)[
            "ram_gb"
        ]
        assert "%.2f GB" % ram_gb in review
        for key in ENGINE_PREFERENCE_ORDER:
            assert engine(global_config, key).value in review
