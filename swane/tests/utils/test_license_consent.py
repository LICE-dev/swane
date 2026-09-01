import os
import sys
from types import SimpleNamespace

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
    monkeypatch.setattr(
        lc, "fetch_online_license", lambda *a, **k: ("ONLINE TEXT", False)
    )
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
    monkeypatch.setattr(
        lc, "fetch_online_license", lambda *a, **k: ("ONLINE TEXT", False)
    )
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.ONLINE
    assert result.show_source_warning is False


def test_resolve_falls_back_to_bundled_when_offline(tmp_path, monkeypatch):
    info = _fake_info(tmp_path, installed=None)
    monkeypatch.setattr(lc, "fetch_online_license", lambda *a, **k: None)
    monkeypatch.setattr(
        LR, "bundled_license_path", lambda i: str(tmp_path / "bundled.txt")
    )
    (tmp_path / "bundled.txt").write_text("BUNDLED TEXT", encoding="utf-8")
    monkeypatch.setattr(lc, "bundled_license_path", LR.bundled_license_path)
    result = lc.resolve_license_text(info, {})
    assert result.source is lc.LicenseSource.BUNDLED
    assert "BUNDLED TEXT" in result.text


class _FakeDM:
    def __init__(self, fsl=True, fs=True, dcm=True, antspyx=True, antspynet=True):
        self._fsl, self._fs, self._dcm, self._antspyx, self._antspynet = (
            fsl,
            fs,
            dcm,
            antspyx,
            antspynet,
        )

    def is_fsl(self):
        return self._fsl

    def is_freesurfer(self):
        return self._fs

    def is_dcm2niix(self):
        return self._dcm

    def is_antspyx(self):
        return self._antspyx

    def is_antspynet(self):
        return self._antspynet


class _FakeConfig:
    def __init__(self, accepted=None, slicer_path="", slicer_version=""):
        self._accepted = accepted or {}
        self._slicer_path, self._slicer_version = slicer_path, slicer_version

    def get_accepted_license_version(self, tool_id):
        return self._accepted.get(tool_id, "")

    def get_slicer_path(self):
        return self._slicer_path

    def get_slicer_version(self):
        return self._slicer_version


def _patch_versions(
    monkeypatch,
    fsl="6.0.6",
    fs="7.3.2",
    dcm="v1.0.20241211",
    antspyx="0.6.3",
    antspynet="0.2.4",
):
    monkeypatch.setattr(lc, "_fsl_version", lambda: fsl)
    monkeypatch.setattr(lc, "_freesurfer_version", lambda: fs)
    monkeypatch.setattr(lc, "_dcm2niix_version", lambda: dcm)
    monkeypatch.setattr(lc, "_antspyx_version", lambda: antspyx)
    monkeypatch.setattr(lc, "_antspynet_version", lambda: antspynet)
    monkeypatch.setattr(lc, "_is_slicer_detected", lambda config: False)


def test_first_run_all_detected_need_consent(monkeypatch):
    _patch_versions(monkeypatch)
    dm, cfg = _FakeDM(), _FakeConfig()
    assert lc.tools_needing_consent(dm, cfg) == [
        "fsl",
        "freesurfer",
        "dcm2niix",
        "antspyx",
        "antspynet",
    ]


def test_unchanged_versions_need_no_consent(monkeypatch):
    _patch_versions(monkeypatch)
    dm = _FakeDM()
    cfg = _FakeConfig(
        accepted={
            "fsl": "6.0.6",
            "freesurfer": "7.3.2",
            "dcm2niix": "v1.0.20241211",
            "antspyx": "0.6.3",
            "antspynet": "0.2.4",
        }
    )
    assert lc.tools_needing_consent(dm, cfg) == []


def test_tools_needing_consent_reuses_detected_snapshot(monkeypatch):
    dm = _FakeDM()
    cfg = _FakeConfig(accepted={"fsl": "6.0.6"})
    monkeypatch.setattr(
        lc,
        "detected_tool_versions",
        lambda *args: (_ for _ in ()).throw(AssertionError("unexpected re-detection")),
    )

    assert lc.tools_needing_consent(dm, cfg, {"fsl": "6.0.6", "antspyx": "0.6.3"}) == [
        "antspyx"
    ]


def test_upgraded_tool_reprompts_only_that_tool(monkeypatch):
    _patch_versions(monkeypatch, fsl="6.0.7")
    dm = _FakeDM()
    cfg = _FakeConfig(
        accepted={
            "fsl": "6.0.6",
            "freesurfer": "7.3.2",
            "dcm2niix": "v1.0.20241211",
            "antspyx": "0.6.3",
            "antspynet": "0.2.4",
        }
    )
    assert lc.tools_needing_consent(dm, cfg) == ["fsl"]


def test_undeterminable_version_uses_sentinel(monkeypatch):
    _patch_versions(monkeypatch, fsl=None)
    dm = _FakeDM(fs=False, dcm=False, antspyx=False, antspynet=False)
    cfg = _FakeConfig()
    assert lc.detected_tool_versions(dm, cfg) == {"fsl": lc.UNKNOWN_VERSION}


def test_dcm2niix_version_reads_package_attribute(monkeypatch):
    fake_dcm2niix = SimpleNamespace(__version__="1.0.20260724")
    monkeypatch.setitem(sys.modules, "dcm2niix", fake_dcm2niix)
    assert lc._dcm2niix_version() == "1.0.20260724"


def test_dcm2niix_version_none_when_package_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "dcm2niix", None)
    assert lc._dcm2niix_version() is None


def test_dcm2niix_version_does_not_spawn_subprocess(monkeypatch):
    """The pipeline (CustomDcm2niix) runs the binary bundled by the pip
    package, not whatever ``dcm2niix`` resolves to on PATH, so the version
    used for license consent must come from the package attribute only -
    never from nipype's CommandLine-based Info.version() (a subprocess
    spawn that also targets the wrong, possibly absent, PATH binary).
    """
    fake_dcm2niix = SimpleNamespace(__version__="1.0.20260724")
    monkeypatch.setitem(sys.modules, "dcm2niix", fake_dcm2niix)
    if "nipype.interfaces" in sys.modules:
        monkeypatch.delitem(sys.modules, "nipype.interfaces", raising=False)
    monkeypatch.setitem(sys.modules, "nipype", None)
    assert lc._dcm2niix_version() == "1.0.20260724"


def test_detected_versions_reuse_dependency_check_results(monkeypatch):
    dm = _FakeDM(dcm=False, antspynet=False)
    dm.fsl = SimpleNamespace(detected_version="6.0.6")
    dm.freesurfer = SimpleNamespace(detected_version="7.3.2")
    dm.antspyx = SimpleNamespace(detected_version="0.6.3")
    cfg = _FakeConfig()
    monkeypatch.setattr(lc, "_is_slicer_detected", lambda config: False)
    monkeypatch.setattr(
        lc,
        "_fsl_version",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected FSL check")),
    )
    monkeypatch.setattr(
        lc,
        "_freesurfer_version",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected FreeSurfer check")),
    )
    monkeypatch.setattr(
        lc,
        "_antspyx_version",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected ANTs check")),
    )

    assert lc.detected_tool_versions(dm, cfg) == {
        "fsl": "6.0.6",
        "freesurfer": "7.3.2",
        "antspyx": "0.6.3",
    }


def test_antspynet_detected_is_offered(monkeypatch):
    _patch_versions(monkeypatch)
    dm, cfg = _FakeDM(), _FakeConfig()
    assert "antspynet" in lc.detected_tool_versions(dm, cfg)
    assert "antspynet" in lc.tools_needing_consent(dm, cfg)
