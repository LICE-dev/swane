from swane.config.config_enums import RegistrationEngine


class TestRegistrationEngineEnum:
    def test_members_exist(self):
        assert {m.name for m in RegistrationEngine} == {"FSL", "SYNTH", "ANTS"}

    def test_values_are_human_labels(self):
        # values are user-facing strings, not the bare member names
        assert all(isinstance(m.value, str) and m.value for m in RegistrationEngine)


def test_is_antspyx_returns_bool():
    from swane.utils.DependencyManager import DependencyManager

    assert isinstance(DependencyManager.is_antspyx(), bool)


def test_instance_is_antspyx_reuses_cached_status(monkeypatch):
    from swane.utils.DependencyManager import (
        Dependence,
        DependenceStatus,
        DependencyManager,
    )

    manager = DependencyManager.__new__(DependencyManager)
    manager.antspyx = Dependence(DependenceStatus.DETECTED, "detected")
    monkeypatch.setattr(
        DependencyManager,
        "check_antspyx",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected dependency check")),
    )

    assert manager.is_antspyx() is True


def test_ants_ram_requirement_positive():
    from swane.utils.ResourceManager import ResourceManager

    assert ResourceManager.ants_ram_requirements() > 0


def test_engine_pref_defaults_to_ants():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine

    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]
    assert entry.default == RegistrationEngine.ANTS


def test_morph_key_removed():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList

    assert "morph" not in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]


def test_synth_option_gated_on_ram_and_freesurfer():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine

    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]
    # SYNTH option keeps the SynthMorph RAM gate and FreeSurfer-Synth dependency
    assert RegistrationEngine.SYNTH in entry.option_pref_requirement
    assert RegistrationEngine.SYNTH in entry.option_dependency


def test_ants_option_gated_on_antspyx_and_ram():
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine

    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["engine"]
    assert RegistrationEngine.ANTS in entry.option_pref_requirement
    assert RegistrationEngine.ANTS in entry.option_dependency


def test_force_pref_reset_enabled_for_this_upgrade():
    # This release must ship with the reset mechanism actually armed
    # (no monkeypatching), so upgrading users get engine=ANTS.
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.config.config_enums import GlobalPrefCategoryList

    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]["force_pref_reset"]
    assert entry.default == "true"


def test_upgrade_resets_engine_to_ants_default(tmp_path):
    from swane.config.ConfigManager import ConfigManager
    from swane.config.config_enums import GlobalPrefCategoryList, RegistrationEngine

    # A reset is triggered only when the file was written by a different
    # SWANe version, so we persist an old last_swane_version on disk, with
    # engine pinned away from its default. force_pref_reset is NOT
    # monkeypatched here: the shipped default must trigger the reset.
    config = ConfigManager(global_base_folder=str(tmp_path))
    config[GlobalPrefCategoryList.SYNTH]["engine"] = RegistrationEngine.FSL.name
    config[GlobalPrefCategoryList.MAIN]["last_swane_version"] = "0.0.0"
    config.save()

    reset = ConfigManager(global_base_folder=str(tmp_path))
    assert (
        reset.getenum_safe(GlobalPrefCategoryList.SYNTH, "engine")
        == RegistrationEngine.ANTS
    )
