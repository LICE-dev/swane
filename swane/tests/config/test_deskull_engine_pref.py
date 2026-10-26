from swane.config import dependency_policy
from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList
from swane.config.dependency_policy import default_engines
from swane.config.preference_list import GLOBAL_PREFERENCES


def test_deskull_engine_default_follows_fsl_policy():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["deskull_engine"]
    expected = default_engines(dependency_policy.FSL_MANDATORY)["deskull_engine"]
    assert entry.default == expected
    assert entry.value_enum is DeskullEngine


def test_strip_pref_removed():
    assert "strip" not in GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]


def test_antspynet_license_key_exists():
    cat = GLOBAL_PREFERENCES[
        GlobalPrefCategoryList.MAIN
    ]  # same category as other accepted_license_*
    assert "accepted_license_antspynet" in cat
