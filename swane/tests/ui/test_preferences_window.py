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
        # The default RAM per subject (70% of the host RAM) may not fit ANTs
        # on small hosts: give it the largest allocation one subject can have.
        ram_gb = ResourceManager.get_maximum_ram()
        if ram_gb < ResourceManager.ants_ram_requirements():
            pytest.skip("host RAM below the ANTs requirement")
        global_config[GlobalPrefCategoryList.PERFORMANCE]["max_subj"] = "1"
        global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = str(ram_gb)

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


class TestSubjectTabResources:
    """RAM and CPU cores apply to each subject tab: the subject tab limit never
    lowers them."""

    def test_subject_tab_limit_does_not_change_ram_or_cpu(
        self, qtbot, global_config, dependency_manager
    ):
        perf = GlobalPrefCategoryList.PERFORMANCE
        ram_gb = ResourceManager.get_maximum_ram()
        global_config[perf]["max_subj"] = "1"
        global_config[perf]["ram_gb"] = str(ram_gb)
        global_config[perf]["max_subj_cpu"] = "-1"
        window = PreferencesWindow(global_config, dependency_manager, False)
        qtbot.addWidget(window)
        keys = window.input_keys[perf]
        max_subj = window.inputs[keys["max_subj"]].input_field
        ram = window.inputs[keys["ram_gb"]].input_field
        cpu = window.inputs[keys["max_subj_cpu"]].input_field

        assert max_subj.maximum() == ResourceManager.MAX_PARALLEL_SUBJECTS
        max_subj.setValue(ResourceManager.MAX_PARALLEL_SUBJECTS)
        assert ram.maximum() == pytest.approx(ResourceManager.get_maximum_ram())
        assert ram.value() == pytest.approx(ram_gb, abs=0.01)
        assert cpu.minimum() == -1 and cpu.value() == -1
        assert cpu.specialValueText() != ""

        window.save_preferences()
        assert global_config.get_max_subject_tabs() == (
            ResourceManager.MAX_PARALLEL_SUBJECTS
        )
        assert global_config.getint_safe(perf, "max_subj_cpu") == -1
        assert global_config.getfloat_safe(perf, "ram_gb") == pytest.approx(
            ram_gb, abs=0.01
        )
