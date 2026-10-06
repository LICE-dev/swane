import pytest

from swane.config.config_enums import FmriEngine, GlobalPrefCategoryList
from swane.config.ConfigManager import ConfigManager
from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.nipype_pipeline.interfaces.utils import resolve_fmri_engine
from swane.utils.DependencyManager import DependencyManager
from swane.utils.ResourceManager import ResourceManager


class TestFmriEngineEnum:
    def test_members_exist(self):
        assert {m.name for m in FmriEngine} == {"NILEARN", "FSL"}

    def test_values_are_human_labels(self):
        assert FmriEngine.NILEARN.value == "Python (nilearn/scikit-learn)"
        assert FmriEngine.FSL.value == "FSL (MELODIC/FEAT)"

    def test_persisted_name_unchanged(self):
        assert FmriEngine["NILEARN"] is FmriEngine.NILEARN


class TestDependencyManagerNilearn:
    def test_is_nilearn_returns_bool(self):
        assert isinstance(DependencyManager.is_nilearn(), bool)

    def test_is_nilearn_true_when_present(self, monkeypatch):
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: object() if name == "nilearn" else None,
        )
        assert DependencyManager.is_nilearn() is True

    def test_is_nilearn_false_when_absent(self, monkeypatch):
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: None,
        )
        assert DependencyManager.is_nilearn() is False


class TestResolveFmriEngine:
    def test_default_returns_nilearn_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(DependencyManager, "is_nilearn", lambda: True)
        monkeypatch.setattr(DependencyManager, "is_fsl", lambda self=None: True)
        config = ConfigManager(global_base_folder=str(tmp_path))

        # Test both ConfigManager and section passing
        assert resolve_fmri_engine(config) == FmriEngine.NILEARN
        synth = config[GlobalPrefCategoryList.SYNTH]
        assert resolve_fmri_engine(synth) == FmriEngine.NILEARN

    def test_nilearn_falls_back_to_fsl_when_nilearn_unavailable(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(DependencyManager, "is_nilearn", lambda: False)
        monkeypatch.setattr(DependencyManager, "is_fsl", lambda self=None: True)
        config = ConfigManager(global_base_folder=str(tmp_path))

        assert resolve_fmri_engine(config) == FmriEngine.FSL
        synth = config[GlobalPrefCategoryList.SYNTH]
        assert resolve_fmri_engine(synth) == FmriEngine.FSL

    def test_fsl_selected_honoured_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(DependencyManager, "is_nilearn", lambda: True)
        monkeypatch.setattr(DependencyManager, "is_fsl", lambda self=None: True)
        config = ConfigManager(global_base_folder=str(tmp_path))
        config[GlobalPrefCategoryList.SYNTH]["fmri_engine"] = FmriEngine.FSL.name

        assert resolve_fmri_engine(config) == FmriEngine.FSL
        synth = config[GlobalPrefCategoryList.SYNTH]
        assert resolve_fmri_engine(synth) == FmriEngine.FSL

    def test_fsl_falls_back_to_nilearn_when_fsl_unavailable(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(DependencyManager, "is_nilearn", lambda: True)
        monkeypatch.setattr(DependencyManager, "is_fsl", lambda self=None: False)
        config = ConfigManager(global_base_folder=str(tmp_path))
        config[GlobalPrefCategoryList.SYNTH]["fmri_engine"] = FmriEngine.FSL.name

        assert resolve_fmri_engine(config) == FmriEngine.NILEARN
        synth = config[GlobalPrefCategoryList.SYNTH]
        assert resolve_fmri_engine(synth) == FmriEngine.NILEARN


class TestFmriEnginePreference:
    def test_pref_registered_under_synth(self):
        assert "fmri_engine" in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]
        entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["fmri_engine"]
        assert entry.default == FmriEngine.NILEARN
        assert entry.value_enum == FmriEngine
        assert entry.section is True

    def test_pref_dependencies_and_requirements(self):
        entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["fmri_engine"]
        assert FmriEngine.FSL in entry.option_dependency
        assert entry.option_dependency[FmriEngine.FSL][0] == "is_fsl"

        assert FmriEngine.NILEARN in entry.option_dependency
        assert entry.option_dependency[FmriEngine.NILEARN][0] == "is_nilearn"

        assert FmriEngine.NILEARN in entry.option_pref_requirement
        assert ResourceManager.nilearn_fmri_ram_requirements() in [
            val
            for _, val in entry.option_pref_requirement[FmriEngine.NILEARN][
                GlobalPrefCategoryList.PERFORMANCE
            ]
        ]

    def test_pref_round_trips_through_config_manager(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        synth = config[GlobalPrefCategoryList.SYNTH]
        assert synth.getenum_safe("fmri_engine") == FmriEngine.NILEARN

        # Mutate to FSL and save
        synth["fmri_engine"] = FmriEngine.FSL.name
        config.save()

        # Reload in a clean ConfigManager
        reloaded = ConfigManager(global_base_folder=str(tmp_path))
        reloaded_synth = reloaded[GlobalPrefCategoryList.SYNTH]
        assert reloaded_synth.getenum_safe("fmri_engine") == FmriEngine.FSL
