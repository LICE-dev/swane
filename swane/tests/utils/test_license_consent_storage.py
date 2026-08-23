def test_accepted_license_version_roundtrip(global_config):
    assert global_config.get_accepted_license_version("fsl") == ""
    global_config.set_accepted_license_version("fsl", "6.0.6")
    assert global_config.get_accepted_license_version("fsl") == "6.0.6"


def test_accepted_license_version_unknown_tool_is_empty(global_config):
    assert global_config.get_accepted_license_version("not_a_tool") == ""
