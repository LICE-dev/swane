import os
from swane.utils import license_consent as lc
from swane.utils import LicenseReference as LR


def _fake_info(tmp_path, installed=None):
    return LR.LicenseInfo(
        tool_id="fsl",
        display_name="FSL",
        official_url="https://example.invalid/license",
        is_html_online=False,
        installed_path_candidates=lambda ctx: [installed] if installed else [],
        bundled_filename="fsl.txt",
    )


def test_resolve_prefers_installed(tmp_path, monkeypatch):
    installed = tmp_path / "LICENSE"
    installed.write_text("INSTALLED TEXT", encoding="utf-8")
    info = _fake_info(tmp_path, installed=str(installed))
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.INSTALLED
    assert "INSTALLED TEXT" in result.text


def test_resolve_falls_back_to_online(tmp_path, monkeypatch):
    info = _fake_info(tmp_path, installed=None)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: ("ONLINE TEXT", False))
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.ONLINE
    assert "ONLINE TEXT" in result.text


def test_resolve_falls_back_to_bundled_when_offline(tmp_path, monkeypatch):
    info = _fake_info(tmp_path, installed=None)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: None)
    monkeypatch.setattr(LR, "bundled_license_path", lambda i: str(tmp_path / "bundled.txt"))
    (tmp_path / "bundled.txt").write_text("BUNDLED TEXT", encoding="utf-8")
    monkeypatch.setattr(lc, "bundled_license_path", LR.bundled_license_path)
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.BUNDLED
    assert "BUNDLED TEXT" in result.text
