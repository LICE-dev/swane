"""Unit tests for the xtract/tractography capability probes."""

from swane.tests.prerelease import capabilities as caps_mod
from swane.tests.prerelease.capabilities import Capabilities


class _DM:
    def __init__(self, fsl):
        self._fsl = fsl

    def is_fsl(self):
        return self._fsl


def _caps():
    return Capabilities(cores=4, ram_gb=14.0)


def test_xtract_false_without_fsl(monkeypatch, tmp_path):
    (tmp_path / "cst_l").mkdir()
    monkeypatch.setattr(caps_mod, "XTRACT_DATA_DIR", str(tmp_path))
    caps = _caps()
    caps_mod._probe_xtract(_DM(False), caps)
    assert not caps.has("xtract")
    assert "FSL" in caps.items["xtract"].reason


def test_xtract_true_with_fsl_and_protocol_dir(monkeypatch, tmp_path):
    (tmp_path / "cst_l").mkdir()
    monkeypatch.setattr(caps_mod, "XTRACT_DATA_DIR", str(tmp_path))
    caps = _caps()
    caps_mod._probe_xtract(_DM(True), caps)
    assert caps.has("xtract")
    assert str(tmp_path) in caps.items["xtract"].reason


def test_xtract_false_with_fsl_but_no_protocol_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(caps_mod, "XTRACT_DATA_DIR", str(tmp_path))
    caps = _caps()
    caps_mod._probe_xtract(_DM(True), caps)
    assert not caps.has("xtract")


def test_tractography_true_with_dipy_only():
    caps = _caps()
    caps.add("xtract", False, "x")
    caps.add("dipy", True, "d")
    caps_mod._probe_tractography(caps)
    assert caps.has("tractography")


def test_tractography_false_when_neither():
    caps = _caps()
    caps.add("xtract", False, "x")
    caps.add("dipy", False, "d")
    caps_mod._probe_tractography(caps)
    assert not caps.has("tractography")
