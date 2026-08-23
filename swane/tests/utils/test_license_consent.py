import os
from swane.utils import license_consent as lc
from swane.utils import LicenseReference as LR


def _fake_info(tmp_path, installed=None, online_is_official=False):
    return LR.LicenseInfo(
        tool_id="fsl",
        display_name="FSL",
        official_url="https://example.invalid/license",
        is_html_online=False,
        installed_path_candidates=lambda ctx: [installed] if installed else [],
        bundled_filename="fsl.txt",
        online_is_official=online_is_official,
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
    # By default online is a fallback -> warn the user
    assert result.show_source_warning is True


def test_license_link_url_prefers_local_file(tmp_path):
    f = tmp_path / "LICENCE.FSL"
    f.write_text("x", encoding="utf-8")
    info = _fake_info(tmp_path, installed=str(f))
    url = lc.license_link_url(info, {})
    assert url.startswith("file://")
    assert url.endswith("LICENCE.FSL")


def test_license_link_url_falls_back_to_official(tmp_path):
    info = _fake_info(tmp_path, installed=None)
    assert lc.license_link_url(info, {}) == "https://example.invalid/license"


def test_version_with_license_appends_link(monkeypatch):
    monkeypatch.setattr(lc, "license_link_url", lambda info, ctx: "http://x/lic")
    out = lc.version_with_license("fsl", "6.0.6")
    assert out.startswith("6.0.6 - ")
    assert 'href="http://x/lic"' in out
    assert "license" in out


def test_version_with_license_no_version_returns_unchanged():
    assert lc.version_with_license("fsl", "") == ""
    assert lc.version_with_license("fsl", None) is None


def test_resolve_online_official_source_suppresses_warning(tmp_path, monkeypatch):
    # Slicer-like: online IS the official source, so no "installed not found" warning
    info = _fake_info(tmp_path, installed=None, online_is_official=True)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: ("ONLINE TEXT", False))
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.ONLINE
    assert result.show_source_warning is False


def test_resolve_falls_back_to_bundled_when_offline(tmp_path, monkeypatch):
    info = _fake_info(tmp_path, installed=None)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: None)
    monkeypatch.setattr(LR, "bundled_license_path", lambda i: str(tmp_path / "bundled.txt"))
    (tmp_path / "bundled.txt").write_text("BUNDLED TEXT", encoding="utf-8")
    monkeypatch.setattr(lc, "bundled_license_path", LR.bundled_license_path)
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.BUNDLED
    assert "BUNDLED TEXT" in result.text


class _FakeDM:
    def __init__(self, fsl=True, fs=True, dcm=True):
        self._fsl, self._fs, self._dcm = fsl, fs, dcm
    def is_fsl(self): return self._fsl
    def is_freesurfer(self): return self._fs
    def is_dcm2niix(self): return self._dcm


class _FakeConfig:
    def __init__(self, accepted=None, slicer_path="", slicer_version=""):
        self._accepted = accepted or {}
        self._slicer_path, self._slicer_version = slicer_path, slicer_version
    def get_accepted_license_version(self, tool_id): return self._accepted.get(tool_id, "")
    def get_slicer_path(self): return self._slicer_path
    def get_slicer_version(self): return self._slicer_version


def _patch_versions(monkeypatch, fsl="6.0.6", fs="7.3.2", dcm="v1.0.20241211"):
    monkeypatch.setattr(lc, "_fsl_version", lambda: fsl)
    monkeypatch.setattr(lc, "_freesurfer_version", lambda: fs)
    monkeypatch.setattr(lc, "_dcm2niix_version", lambda: dcm)
    monkeypatch.setattr(lc, "_is_slicer_detected", lambda config: False)


def test_first_run_all_detected_need_consent(monkeypatch):
    _patch_versions(monkeypatch)
    dm, cfg = _FakeDM(), _FakeConfig()
    assert lc.tools_needing_consent(dm, cfg) == ["fsl", "freesurfer", "dcm2niix"]


def test_unchanged_versions_need_no_consent(monkeypatch):
    _patch_versions(monkeypatch)
    dm = _FakeDM()
    cfg = _FakeConfig(accepted={"fsl": "6.0.6", "freesurfer": "7.3.2", "dcm2niix": "v1.0.20241211"})
    assert lc.tools_needing_consent(dm, cfg) == []


def test_upgraded_tool_reprompts_only_that_tool(monkeypatch):
    _patch_versions(monkeypatch, fsl="6.0.7")
    dm = _FakeDM()
    cfg = _FakeConfig(accepted={"fsl": "6.0.6", "freesurfer": "7.3.2", "dcm2niix": "v1.0.20241211"})
    assert lc.tools_needing_consent(dm, cfg) == ["fsl"]


def test_undeterminable_version_uses_sentinel(monkeypatch):
    _patch_versions(monkeypatch, fsl=None)
    dm = _FakeDM(fs=False, dcm=False)
    cfg = _FakeConfig()
    assert lc.detected_tool_versions(dm, cfg) == {"fsl": lc.UNKNOWN_VERSION}
