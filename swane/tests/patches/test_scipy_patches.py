"""Tests for the macOS SciPy PROPACK mock in swane.patches.scipy_patches."""

import importlib.metadata
import sys

import pytest

from swane.patches import scipy_patches

PROPACK = "scipy.sparse.linalg._propack"


@pytest.fixture
def fresh_patch(monkeypatch):
    """Run apply_scipy_patches as on first import, restoring sys.modules after."""
    monkeypatch.setattr(scipy_patches, "_SCIPY_PATCHED", False)
    saved = sys.modules.pop(PROPACK, None)
    yield
    sys.modules.pop(PROPACK, None)
    if saved is not None:
        sys.modules[PROPACK] = saved


def _apply(monkeypatch, platform, version):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(scipy_patches, "_installed_scipy_version", lambda: version)
    scipy_patches.apply_scipy_patches()
    return sys.modules.get(PROPACK)


@pytest.mark.parametrize("version", [(1, 15, 3), (1, 16, 0), (1, 17, 0)])
def test_old_scipy_on_macos_is_mocked(fresh_patch, monkeypatch, version):
    module = _apply(monkeypatch, "darwin", version)
    assert isinstance(module, scipy_patches.types.ModuleType)
    assert type(module).__name__ == "MockPropackModule"
    assert scipy_patches._SCIPY_PATCHED


@pytest.mark.parametrize("version", [(1, 17, 1), (1, 18), (2, 0, 0), None])
def test_fixed_or_missing_scipy_on_macos_is_not_mocked(
    fresh_patch, monkeypatch, version
):
    """scipy >= 1.17.1 has a working PROPACK that the mock would shadow."""
    assert _apply(monkeypatch, "darwin", version) is None
    assert scipy_patches._SCIPY_PATCHED


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_other_platforms_are_never_mocked(fresh_patch, monkeypatch, platform):
    assert _apply(monkeypatch, platform, (1, 15, 3)) is None


@pytest.mark.parametrize(
    "raw, parsed",
    [
        ("1.15.3", (1, 15, 3)),
        ("1.17.1", (1, 17, 1)),
        ("1.18.0rc1", (1, 18, 0)),
        ("1.17.1.dev0+git", (1, 17, 1)),
        ("unknown", None),
    ],
)
def test_installed_scipy_version_parsing(monkeypatch, raw, parsed):
    monkeypatch.setattr(importlib.metadata, "version", lambda name: raw)
    assert scipy_patches._installed_scipy_version() == parsed


def test_installed_scipy_version_missing(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert scipy_patches._installed_scipy_version() is None
