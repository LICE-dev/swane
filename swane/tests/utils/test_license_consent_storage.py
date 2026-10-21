import os


def test_accepted_license_version_roundtrip(global_config):
    assert global_config.get_accepted_license_version("fsl") == ""
    global_config.set_accepted_license_version("fsl", "6.0.6")
    assert global_config.get_accepted_license_version("fsl") == "6.0.6"


def test_accepted_license_version_unknown_tool_is_empty(global_config):
    assert global_config.get_accepted_license_version("not_a_tool") == ""


def test_accepted_license_version_nilearn(global_config):
    assert global_config.get_accepted_license_version("nilearn") == ""
    global_config.set_accepted_license_version("nilearn", "0.10.4")
    assert global_config.get_accepted_license_version("nilearn") == "0.10.4"


def test_every_consent_tool_has_a_declared_acceptance_key(global_config):
    """Every tool the consent gate checks persists its acceptance under a key
    declared in the schema, not as an undeclared option."""
    from swane.config.config_enums import GlobalPrefCategoryList
    from swane.config.preference_list import GLOBAL_PREFERENCES
    from swane.utils.LicenseReference import TOOL_IDS
    from swane.utils.license_consent import tools_needing_consent

    detected = {tool_id: "1.0" for tool_id in TOOL_IDS}
    checked = tools_needing_consent(None, global_config, detected)
    assert set(checked) == set(TOOL_IDS)
    main = GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]
    assert [t for t in checked if "accepted_license_" + t not in main] == []


def test_accepted_license_versions_survive_reload(global_config):
    from swane.config.ConfigManager import ConfigManager
    from swane.utils.LicenseReference import TOOL_IDS

    for tool_id in TOOL_IDS:
        global_config.set_accepted_license_version(tool_id, tool_id + "-1.0")
    global_config.save()

    reloaded = ConfigManager(
        global_base_folder=os.path.dirname(global_config.config_file)
    )

    for tool_id in TOOL_IDS:
        assert reloaded.get_accepted_license_version(tool_id) == tool_id + "-1.0"
