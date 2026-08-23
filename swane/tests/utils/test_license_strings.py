from swane import strings


def test_license_strings_present_and_english():
    assert "research tool" in strings.license_consent_banner.lower()
    assert "not a medical device" in strings.license_consent_banner.lower()
    assert "{current}" in strings.license_consent_progress
    assert "{total}" in strings.license_consent_progress
    assert "{tool}" in strings.license_consent_source_online
    assert "{tool}" in strings.license_consent_source_bundled
    assert strings.license_consent_accept_button
