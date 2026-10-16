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
import swane.ui.PreferenceWizardWindow as wizard_module
from swane.ui.PreferenceWizardWindow import (
    PreferenceWizardWindow,
    UserPreferences,
    ENGINE_PREFERENCE_ORDER,
    RESOURCE_LEVELS,
)

PERF = GlobalPrefCategoryList.PERFORMANCE
SYNTH = GlobalPrefCategoryList.SYNTH
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
    entry = GLOBAL_PREFERENCES[SYNTH][key]
    for pref, threshold in entry.option_pref_requirement[option][PERF]:
        if pref == "ram_gb":
            return threshold


def set_ram(global_config, ram_gb):
    global_config[PERF]["ram_gb"] = str(ram_gb)


def engine(global_config, key):
    return global_config.getenum_safe(SYNTH, key)


def resources(ram_gb):
    return {"ram_gb": ram_gb, "max_subj_cpu": 1, "max_subj": 1}


@pytest.fixture(autouse=True)
def not_mac(monkeypatch):
    """Recommendations differ on macOS (no Synth engines): pin the platform."""
    monkeypatch.setattr(wizard_module, "is_mac", lambda: False)


@pytest.fixture
def wizard(qtbot, global_config, dependency_manager, monkeypatch):
    """A wizard whose profile does not overwrite the RAM set by the test, and
    whose engine choices are left to the recommendation."""
    wizard = PreferenceWizardWindow(global_config, dependency_manager)
    qtbot.addWidget(wizard)
    monkeypatch.setattr(
        global_config, "apply_resource_profile", lambda profile, parallel=1: None
    )
    wizard.user_prefs.engines = {}
    return wizard


class TestPreferenceWizard:

    def test_build(self, qtbot, global_config, dependency_manager):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert wizard.windowTitle() != ""
        assert isinstance(wizard.user_prefs, UserPreferences)
        assert wizard._stack.count() >= 5

    def test_navigation_next_then_back(self, qtbot, global_config, dependency_manager):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        start = wizard._stack.currentIndex()
        wizard._go_next()
        assert wizard._stack.currentIndex() == start + 1
        wizard._go_back()
        assert wizard._stack.currentIndex() == start

    def test_freesurfer_checkboxes_update_preferences(
        self, qtbot, global_config, dependency_manager
    ):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        page = wizard._page_freesurfer_outputs()
        qtbot.addWidget(page)

        wizard._cb_freesurfer_cortical_parcellation.setChecked(True)
        assert wizard.user_prefs.cortical_parcellation_enabled is True
        wizard._cb_freesurfer_full_reconall.setChecked(True)
        assert wizard.user_prefs.full_reconall_enabled is True

    def test_synth_checkbox_only_with_synth_tools(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth")
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        page = wizard._page_freesurfer_outputs()
        qtbot.addWidget(page)
        wizard._cb_freesurfer_synth.setChecked(True)
        assert wizard.user_prefs.use_synth_freesurfer is True

        set_tools(monkeypatch, dependency_manager)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        page = wizard._page_freesurfer_outputs()
        qtbot.addWidget(page)
        assert not hasattr(wizard, "_cb_freesurfer_synth")

    def test_synthseg_requires_synth_tools_and_sufficient_ram(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth")
        threshold = dict(
            WF_PREFERENCES[DataInputList.T13D][
                "freesurfer_step"
            ].option_pref_requirement[FreesurferStep.SYNTHSEG][PERF]
        )["ram_gb"]
        wizard.user_prefs.freesurfer_capable = True
        wizard.user_prefs.synth_capable = True
        wizard.user_prefs.cortical_parcellation_enabled = True
        wizard.user_prefs.use_synth_freesurfer = True

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

        wizard.user_prefs.use_synth_freesurfer = False
        wizard._apply_settings_config()
        assert (
            global_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            == FreesurferStep.AUTORECON_PIAL
        )

    def test_welcome_page_warns_on_windows_only(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
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


class TestResourceShare:
    """The chosen share of the computer is split among the subjects analysed at
    the same time: all the subject tabs together never exceed its RAM or its
    CPU cores."""

    @pytest.mark.parametrize("level", [level for level, _ in RESOURCE_LEVELS])
    def test_subjects_never_exceed_the_share(self, level):
        budget_ram, budget_cpu = ConfigManager.get_resource_budget(level)
        assert budget_ram <= ResourceManager.get_maximum_ram()
        max_parallel = ConfigManager.get_max_parallel_subjects(level)
        assert 1 <= max_parallel <= ResourceManager.get_max_parallel_subjects()
        assert max_parallel <= budget_cpu or max_parallel == 1
        for parallel in range(1, ResourceManager.MAX_PARALLEL_SUBJECTS + 3):
            values = ConfigManager.get_resource_profile_values(level, parallel)
            assert values["max_subj"] == min(parallel, max_parallel)
            assert values["ram_gb"] * values["max_subj"] <= budget_ram
            assert values["max_subj_cpu"] * values["max_subj"] <= budget_cpu
            assert values["ram_gb"] >= ResourceManager.get_minimum_subject_ram()
            assert values["max_subj_cpu"] >= 1

    def test_levels_are_50_70_90_percent(self):
        total = ResourceManager.total_memory_gb()
        budgets = [ConfigManager.get_resource_budget(l)[0] for l, _ in RESOURCE_LEVELS]
        assert budgets == pytest.approx(
            [total * p / 100 for p in (50, 70, 90)], abs=0.02
        )

    def test_parallel_subjects_limited_by_cores(self, monkeypatch):
        monkeypatch.setattr(
            ConfigManager, "get_resource_budget", staticmethod(lambda profile: (64, 3))
        )
        monkeypatch.setattr(ResourceManager, "get_max_cpu", staticmethod(lambda: 8))
        assert ConfigManager.get_max_parallel_subjects(PerformanceProfile.BALANCED) == 3
        values = ConfigManager.get_resource_profile_values(
            PerformanceProfile.BALANCED, 5
        )
        assert values["max_subj"] == 3 and values["max_subj_cpu"] == 1

    def test_split_ram_is_a_valid_preference_value(self):
        # The Preferences window must accept the RAM of any split share
        low, high = GLOBAL_PREFERENCES[PERF]["ram_gb"].range
        assert low == ResourceManager.get_minimum_subject_ram()
        assert high == ResourceManager.get_maximum_ram()
        assert GLOBAL_PREFERENCES[PERF]["max_subj"].range == [
            1,
            ResourceManager.get_max_parallel_subjects(),
        ]
        for level, _ in RESOURCE_LEVELS:
            values = ConfigManager.get_resource_profile_values(
                level, ResourceManager.MAX_PARALLEL_SUBJECTS
            )
            assert low <= values["ram_gb"] <= high

    def _computer(self, monkeypatch, alerts, ram_gb, cpu):
        monkeypatch.setattr(
            ConfigManager,
            "get_resource_budget",
            staticmethod(lambda profile: (ram_gb, cpu)),
        )
        monkeypatch.setattr(ResourceManager, "get_max_cpu", staticmethod(lambda: 64))
        monkeypatch.setattr(
            PreferenceWizardWindow,
            "_alert_low_subject_resources",
            lambda self, warning: alerts.append(warning),
        )

    def test_alert_when_new_subject_goes_below_low_ram(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        # 6 GB share: below 2 GB per subject from 4 subjects
        alerts = []
        self._computer(monkeypatch, alerts, 6, 20)
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)
        assert wizard._parallel_spin.maximum() == ResourceManager.MAX_PARALLEL_SUBJECTS

        wizard._parallel_spin.setValue(3)
        assert alerts == []
        assert wizard._low_resources_label.isHidden()

        wizard._parallel_spin.setValue(4)
        assert len(alerts) == 1 and "GB of RAM" in alerts[0]
        assert not wizard._low_resources_label.isHidden()

        wizard._parallel_spin.setValue(5)
        assert len(alerts) == 2

        # Removing a subject or changing level never pops the alert
        wizard._parallel_spin.setValue(4)
        wizard._perf_buttons[PerformanceProfile.LOW_RESOURCE].setChecked(True)
        assert len(alerts) == 2

    def test_alert_when_new_subject_goes_below_low_cpu(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        # 4 cores share: at most 4 subjects, below 2 cores per subject from 3
        alerts = []
        self._computer(monkeypatch, alerts, 64, 4)
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)
        assert wizard._parallel_spin.maximum() == 4

        wizard._parallel_spin.setValue(2)
        assert alerts == []
        assert wizard._low_resources_label.isHidden()

        wizard._parallel_spin.setValue(3)
        assert len(alerts) == 1 and "CPU core" in alerts[0]
        assert not wizard._low_resources_label.isHidden()

        # Still 1 core each: nothing lowered, no new alert
        wizard._parallel_spin.setValue(4)
        assert len(alerts) == 1
        assert wizard.user_prefs.parallel_subjects == 4

    def test_apply_writes_the_split_share(
        self, qtbot, global_config, dependency_manager
    ):
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)
        level = PerformanceProfile.MAX_PERF
        parallel = ConfigManager.get_max_parallel_subjects(level)
        wizard.user_prefs.performance_profile = level
        wizard.user_prefs.parallel_subjects = parallel

        wizard._apply_settings_config()

        expected = ConfigManager.get_resource_profile_values(level, parallel)
        assert global_config.getint_safe(PERF, "max_subj") == parallel
        assert global_config.getfloat_safe(PERF, "ram_gb") == expected["ram_gb"]
        assert (
            global_config.getint_safe(PERF, "max_subj_cpu") == expected["max_subj_cpu"]
        )


class TestInitialChoices:
    """Later runs start from the current configuration; the first run starts
    from the recommendations."""

    def _configure(self, global_config):
        global_config[PERF]["max_subj"] = "2"
        global_config[PERF]["ram_gb"] = "5"
        global_config[SYNTH]["tractography_engine"] = TractographyEngine.FSL_XTRACT.name
        global_config[DataInputList.T13D][
            "freesurfer_step"
        ] = FreesurferStep.RECONALL.name
        global_config[DataInputList.T13D]["hippo_amyg_labels"] = "true"

    def test_rerun_shows_current_settings(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        self._configure(global_config)
        monkeypatch.setattr(dependency_manager, "is_freesurfer", lambda: True)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_matlab", lambda: True)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)

        prefs = wizard.user_prefs
        expected_parallel = min(
            2, ConfigManager.get_max_parallel_subjects(prefs.performance_profile)
        )
        assert prefs.parallel_subjects == expected_parallel
        assert wizard._parallel_spin.value() == expected_parallel
        assert prefs.engines["tractography_engine"] is TractographyEngine.FSL_XTRACT
        assert prefs.full_reconall_enabled
        assert prefs.hippocampal_segmentation_enabled
        assert not prefs.surfaces_enabled
        assert wizard._cb_freesurfer_full_reconall.isChecked()
        assert wizard._cb_freesurfer_hippocampal_segmentation.isChecked()

    def test_rerun_picks_the_closest_level(
        self, qtbot, global_config, dependency_manager
    ):
        level = PerformanceProfile.LOW_RESOURCE
        global_config.apply_resource_profile(level, 2)
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert wizard.user_prefs.performance_profile is level
        assert wizard._perf_buttons[level].isChecked()

    def test_first_run_uses_recommendations(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        self._configure(global_config)
        set_tools(monkeypatch, dependency_manager, "is_dipy", "is_fsl")
        monkeypatch.setattr(dependency_manager, "is_freesurfer", lambda: True)
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)

        prefs = wizard.user_prefs
        assert prefs.performance_profile is PerformanceProfile.BALANCED
        assert prefs.parallel_subjects == 1
        assert not prefs.full_reconall_enabled
        ram_gb = ConfigManager.get_resource_profile_values(prefs.performance_profile)[
            "ram_gb"
        ]
        assert (
            prefs.engines["tractography_engine"]
            == wizard._select_engine("tractography_engine", ram_gb)[0]
        )


class TestRecommendedEngines:
    """Without a user choice, each engine is the first installed tool of its
    recommendation order that fits the RAM per subject."""

    def test_antspynet_recommended(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_antspynet", "is_fsl")
        set_ram(
            global_config, ram_requirement("deskull_engine", DeskullEngine.ANTSPYNET)
        )
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.ANTSPYNET

    def test_synth_engines_not_recommended_on_macos(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth", "is_fsl")
        set_ram(global_config, 64)
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.SYNTHSTRIP
        assert engine(global_config, "engine") == RegistrationEngine.SYNTH

        monkeypatch.setattr(wizard_module, "is_mac", lambda: True)
        wizard.user_prefs.engines = {}
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.BET
        assert engine(global_config, "engine") == RegistrationEngine.FSL

    def test_fsl_mandatory_recommends_bet(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
        set_tools(monkeypatch, dependency_manager, *DEPENDENCIES)
        set_ram(global_config, 64)
        wizard._apply_settings_config()
        assert engine(global_config, "deskull_engine") == DeskullEngine.BET

    def test_nothing_installed_keeps_default_and_flags_it(
        self, wizard, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager)
        plan = wizard._build_plan(resources(64))
        default = dependency_policy.default_engines(dependency_policy.FSL_MANDATORY)
        assert plan.engines["deskull_engine"] == default["deskull_engine"]
        assert "deskull_engine" in plan.engine_notes

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

        monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
        set_tools(monkeypatch, dependency_manager, python_tool, "is_fsl")
        assert wizard._select_engine(key, threshold) == (python_engine, "")

        # Python engine does not fit the RAM: FSL takes over
        assert wizard._select_engine(key, threshold - 1) == (fsl_engine, "")

        # No FSL either: the installed engine is kept and flagged
        set_tools(monkeypatch, dependency_manager, python_tool)
        selected, note = wizard._select_engine(key, threshold - 1)
        assert selected == python_engine and note

        # FSL installed but missing the Python tool: FSL
        set_tools(monkeypatch, dependency_manager, "is_fsl")
        assert wizard._select_engine(key, threshold)[0] == fsl_engine

        # FSL mandatory: FSL first even when the Python engine fits
        monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
        set_tools(monkeypatch, dependency_manager, python_tool, "is_fsl")
        assert wizard._select_engine(key, threshold)[0] == fsl_engine

    def test_every_engine_preference_is_offered(self):
        engine_keys = {
            key
            for key, entry in GLOBAL_PREFERENCES[SYNTH].items()
            if entry.value_enum is not None and entry.option_dependency
        }
        assert engine_keys == set(ENGINE_PREFERENCE_ORDER)
        for key, order in ENGINE_PREFERENCE_ORDER.items():
            assert set(order) == set(GLOBAL_PREFERENCES[SYNTH][key].value_enum)

    def test_legacy_keys_are_never_written(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, *DEPENDENCIES)
        wizard._apply_settings_config()
        assert "morph" not in global_config[SYNTH]
        assert "strip" not in global_config[SYNTH]


class TestEnginePage:

    def _enter_engine_page(self, wizard):
        while not hasattr(wizard._stack.currentWidget(), "_wizard_on_enter") or (
            wizard._stack.currentWidget()._wizard_on_enter
            != wizard._refresh_engine_page
        ):
            wizard._go_next()

    def test_unavailable_options_are_disabled(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_dipy", "is_antspyx")
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)
        self._enter_engine_page(wizard)

        combo = wizard._engine_combos["tractography_engine"]
        fsl_item = combo.model().item(combo.findData(TractographyEngine.FSL_XTRACT))
        assert not fsl_item.isEnabled()
        assert fsl_item.toolTip() != ""
        ram_gb = wizard._resources()["ram_gb"]
        dipy_fits = ram_gb >= ram_requirement(
            "tractography_engine", TractographyEngine.DIPY_RECOBUNDLES
        )
        dipy_item = combo.model().item(
            combo.findData(TractographyEngine.DIPY_RECOBUNDLES)
        )
        assert dipy_item.isEnabled() == dipy_fits

    def test_user_choice_is_kept_and_applied(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_dipy", "is_fsl")
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)
        self._enter_engine_page(wizard)

        combo = wizard._engine_combos["tractography_engine"]
        combo.setCurrentIndex(combo.findData(TractographyEngine.FSL_XTRACT))
        assert (
            wizard.user_prefs.engines["tractography_engine"]
            is TractographyEngine.FSL_XTRACT
        )
        wizard._go_back()
        self._enter_engine_page(wizard)
        assert combo.currentData() is TractographyEngine.FSL_XTRACT

        while not wizard._is_review_page():
            wizard._go_next()
        wizard._finish()
        assert (
            engine(global_config, "tractography_engine")
            == TractographyEngine.FSL_XTRACT
        )

    def test_choice_that_no_longer_fits_is_replaced(
        self, wizard, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_dipy", "is_fsl")
        threshold = ram_requirement(
            "tractography_engine", TractographyEngine.DIPY_RECOBUNDLES
        )
        wizard.user_prefs.engines = {
            "tractography_engine": TractographyEngine.DIPY_RECOBUNDLES
        }
        plan = wizard._build_plan(resources(threshold - 1))
        assert plan.engines["tractography_engine"] is TractographyEngine.FSL_XTRACT


class TestPreferenceWizardRerun:
    """Rerunning the wizard turns off what a previous run enabled."""

    def test_synth_reconall_is_reset(
        self, wizard, global_config, dependency_manager, monkeypatch
    ):
        set_tools(monkeypatch, dependency_manager, "is_freesurfer_synth")
        set_ram(global_config, 64)
        wizard.user_prefs.synth_capable = True
        wizard.user_prefs.use_synth_freesurfer = True
        wizard._apply_settings_config()
        assert global_config.getboolean_safe(SYNTH, "reconall")

        wizard.user_prefs.use_synth_freesurfer = False
        wizard._apply_settings_config()
        assert not global_config.getboolean_safe(SYNTH, "reconall")

    def test_hippocampal_subfields_are_reset(self, wizard, global_config):
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
        wizard = PreferenceWizardWindow(
            global_config, dependency_manager, first_run=True
        )
        qtbot.addWidget(wizard)
        while not wizard._is_review_page():
            wizard._go_next()
        review = wizard._review_label.text()

        wizard._finish()
        assert wizard._is_applied_page()

        assert "%.2f GB" % global_config.getfloat_safe(PERF, "ram_gb") in review
        for key in ENGINE_PREFERENCE_ORDER:
            assert engine(global_config, key).value in review
