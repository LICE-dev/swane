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
from swane.utils.DataInputList import DataInputList
from swane.utils.ResourceManager import ResourceManager


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


class TestHideVsGrayOut:
    """A disabled preference is fully hidden when the reason cannot be
    changed from within the same preferences window (an external
    dependency/resource, or a requirement on another window's preference),
    and only grayed out when it could still be unlocked by another
    preference present in this same window.
    """

    def test_resource_gated_entry_is_hidden(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        monkeypatch.setattr(ResourceManager, "is_cuda", lambda: False)

        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)

        x = window.input_keys[GlobalPrefCategoryList.PERFORMANCE]["cuda"]
        entry = window.inputs[x]

        assert entry.label.isHidden() is True
        assert entry.input_field.isHidden() is True

    def test_same_window_requirement_is_grayed_not_hidden(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        # CUDA available (so "cuda" itself is not hidden) but left unchecked
        # (the default), so "max_subj_gpu" -- which requires cuda=True in the
        # very same PERFORMANCE tab -- fails its requirement and must stay
        # visible, just disabled: the user can still fix it from here.
        monkeypatch.setattr(ResourceManager, "is_cuda", lambda: True)

        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)

        cuda_x = window.input_keys[GlobalPrefCategoryList.PERFORMANCE]["cuda"]
        assert window.inputs[cuda_x].label.isHidden() is False

        gpu_x = window.input_keys[GlobalPrefCategoryList.PERFORMANCE]["max_subj_gpu"]
        entry = window.inputs[gpu_x]

        assert entry.label.isHidden() is False
        assert entry.input_field.isHidden() is False
        assert entry.input_field.isEnabled() is False

    def test_dependency_gated_workflow_entry_is_hidden(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        # The generic workflow-preferences window (is_workflow=True, no
        # subject) shares the exact same PreferencesWindow/PreferenceUIEntry
        # code as the subject one.
        monkeypatch.setattr(dependency_manager, "is_freesurfer", lambda: False)

        window = PreferencesWindow(global_config, dependency_manager, True)
        qtbot.addWidget(window)

        x = window.input_keys[DataInputList.T13D]["freesurfer_step"]
        entry = window.inputs[x]

        assert entry.label.isHidden() is True
        assert entry.input_field.isHidden() is True

    @pytest.mark.parametrize("fsl", [True, False])
    def test_resting_state_optional_series_is_hidden_without_fsl(
        self, qtbot, global_config, dependency_manager, monkeypatch, fsl
    ):
        # Resting state runs on FSL (MELODIC) only: without FSL its optional
        # series cannot be enabled.
        monkeypatch.setattr(dependency_manager, "is_fsl", lambda: fsl)

        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)

        optional = window.input_keys[GlobalPrefCategoryList.OPTIONAL_SERIES]
        entry = window.inputs[optional[str(DataInputList.FMRI_RS)]]
        assert entry.input_field.isHidden() is not fsl
        assert entry.label.isHidden() is not fsl
        # The task fMRI series has no external dependency.
        task = window.inputs[optional[str(DataInputList.FMRI_0)]]
        assert task.input_field.isHidden() is False

    def test_same_window_pref_requirement_in_workflow_window_is_grayed(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        # freesurfer_step stays at its default (DISABLED), so
        # hippo_amyg_labels -- which requires freesurfer_step to be
        # RECONALL/AUTORECON_PIAL in the same T13D tab -- must stay visible
        # but grayed, not hidden: the user can still fix it from here.
        monkeypatch.setattr(dependency_manager, "is_freesurfer", lambda: True)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_matlab", lambda: True)

        window = PreferencesWindow(global_config, dependency_manager, True)
        qtbot.addWidget(window)

        x = window.input_keys[DataInputList.T13D]["hippo_amyg_labels"]
        entry = window.inputs[x]

        assert entry.label.isHidden() is False
        assert entry.input_field.isHidden() is False
        assert entry.input_field.isEnabled() is False


class TestSubjectRamLimit:
    """All the subject tabs together never exceed the RAM share or the CPU
    cores: raising the subject tab limit lowers the RAM and CPU cores per
    subject maximum, with an alert when a new subject brings them below
    ResourceManager.LOW_SUBJECT_RAM_GB / LOW_SUBJECT_CPU."""

    def _fields(self, window):
        keys = window.input_keys[GlobalPrefCategoryList.PERFORMANCE]
        return (
            window.inputs[keys["max_subj"]].input_field,
            window.inputs[keys["ram_gb"]],
        )

    def test_ram_maximum_follows_subject_tab_limit(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        alerts = []
        monkeypatch.setattr(
            PreferencesWindow,
            "_alert_low_subject_resources",
            lambda self, w: alerts.append(w),
        )
        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)
        max_subj, ram = self._fields(window)

        max_subj.setValue(1)
        ram.input_field.setValue(ResourceManager.get_maximum_ram())
        assert max_subj.maximum() == ResourceManager.get_max_parallel_subjects()
        for subjects in range(2, max_subj.maximum() + 1):
            max_subj.setValue(subjects)
            limit = ResourceManager.get_max_subject_ram(subjects)
            assert ram.input_field.maximum() == pytest.approx(limit)
            assert ram.input_field.value() * subjects <= (
                ResourceManager.get_maximum_ram() + 1e-6
            )
        assert ram.changed

    def test_alert_when_new_subject_goes_below_low_ram(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        # A 4 GB computer: 3.6 GB share, below 2 GB per subject from 2 subjects
        monkeypatch.setattr(
            ResourceManager, "get_maximum_ram", staticmethod(lambda: 3.6)
        )
        alerts = []
        monkeypatch.setattr(
            PreferencesWindow,
            "_alert_low_subject_resources",
            lambda self, w: alerts.append(w),
        )
        global_config[GlobalPrefCategoryList.PERFORMANCE]["max_subj"] = "1"
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "3.6"
        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)
        max_subj, ram = self._fields(window)
        assert alerts == []

        max_subj.setValue(2)
        assert ram.input_field.value() == pytest.approx(1.8)
        assert len(alerts) == 1 and "GB of RAM" in alerts[0]

        # Removing a subject never alerts
        max_subj.setValue(1)
        assert len(alerts) == 1

    def test_save_enforces_the_limit(self, qtbot, global_config, dependency_manager):
        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)
        perf = GlobalPrefCategoryList.PERFORMANCE
        global_config[perf]["max_subj"] = "99"
        global_config[perf]["ram_gb"] = str(ResourceManager.get_maximum_ram())
        window.save_preferences()
        max_subj = ResourceManager.get_max_parallel_subjects()
        assert global_config.getint_safe(perf, "max_subj") == max_subj
        assert global_config.getfloat_safe(
            perf, "ram_gb"
        ) == ResourceManager.get_max_subject_ram(max_subj)

    def test_cpu_maximum_follows_subject_tab_limit(
        self, qtbot, global_config, dependency_manager, monkeypatch
    ):
        alerts = []
        monkeypatch.setattr(
            PreferencesWindow,
            "_alert_low_subject_resources",
            lambda self, w: alerts.append(w),
        )
        perf = GlobalPrefCategoryList.PERFORMANCE
        global_config[perf]["max_subj"] = "1"
        global_config[perf]["max_subj_cpu"] = "-1"
        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)
        max_subj, _ = self._fields(window)
        cpu = window.inputs[window.input_keys[perf]["max_subj_cpu"]].input_field
        if max_subj.maximum() < 2:
            pytest.skip("single-core host: one subject at a time")

        cores = ResourceManager.get_max_cpu()
        previous = cores
        for subjects in range(2, max_subj.maximum() + 1):
            alerts.clear()
            max_subj.setValue(subjects)
            limit = ResourceManager.get_max_subject_cpu(subjects)
            assert cpu.minimum() == 1 and cpu.specialValueText() == ""
            assert cpu.maximum() == limit
            assert cpu.value() * subjects <= cores
            cpu_alerts = [a for a in alerts if "CPU core" in a]
            expected = cpu.value() < previous and cpu.value() < (
                ResourceManager.LOW_SUBJECT_CPU
            )
            assert bool(cpu_alerts) == expected
            previous = cpu.value()

        max_subj.setValue(1)
        assert cpu.minimum() == -1
        assert cpu.specialValueText() != ""
