from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList
from swane.config.preference_list import GLOBAL_PREFERENCES


def test_deskull_engine_default_is_antspynet():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["deskull_engine"]
    assert entry.default == DeskullEngine.ANTSPYNET
    assert entry.value_enum is DeskullEngine


def test_strip_pref_removed():
    assert "strip" not in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]


def test_antspynet_license_key_exists():
    cat = GLOBAL_PREFERENCES[
        GlobalPrefCategoryList.MAIN
    ]  # same category as other accepted_license_*
    assert "accepted_license_antspynet" in cat
