# -*- coding: utf-8 -*-
"""Monkeypatch for SciPy on macOS to bypass the _spropack zero-fill section bug."""

import importlib.metadata
import re
import sys
import types

_SCIPY_PATCHED = False

# First SciPy whose macOS wheels have no gfortran-built extension module (its
# PROPACK is C): from this release on the real module loads and must be kept.
FIXED_SCIPY_VERSION = (1, 17, 1)


def _installed_scipy_version():
    """
    Return the installed SciPy version as a tuple of ints, without importing SciPy.

    Returns
    -------
    tuple of int or None
        The leading numeric components (``"1.15.3"`` gives ``(1, 15, 3)``), or
        None when SciPy is not installed or its version has no leading number.
    """
    try:
        version = importlib.metadata.version("scipy")
    except importlib.metadata.PackageNotFoundError:
        return None
    match = re.match(r"\d+(?:\.\d+)*", version)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def apply_scipy_patches():
    """
    Install a mock for scipy.sparse.linalg._propack to avoid a crash on macOS.

    Because antspyx (up to 0.6.3) strictly requires scipy < 1.16, pip forces the
    installation of older scipy wheels. These older wheels contain broken binary
    modules (_spropack.cpython-312-darwin.so, etc.) that cause an immediate
    ImportError: dlopen crash with a "__DATA/__thread_bss has a zero-fill section
    type" error on recent macOS versions (like Sequoia or with recent toolchains).

    Since SWANe and Nipype never actually use the 'propack' SVD solver, we can bypass
    this crash entirely by injecting a dummy module into sys.modules BEFORE scipy
    is fully imported.

    The mock covers PROPACK only. On newer macOS releases other gfortran-built
    modules of those wheels (in scipy.integrate and scipy.optimize, which
    scipy.stats imports) fail to load too, and they cannot be mocked because
    they compute real results: the installer (installer/install_swane.sh)
    installs scipy >= 1.17.1 on macOS instead. With that SciPy installed nothing
    is patched, so the real PROPACK module is never shadowed.
    """
    global _SCIPY_PATCHED
    if _SCIPY_PATCHED:
        return

    if sys.platform != "darwin":
        _SCIPY_PATCHED = True
        return

    version = _installed_scipy_version()
    if version is None or version >= FIXED_SCIPY_VERSION:
        _SCIPY_PATCHED = True
        return

    # Check if it has already been patched or imported successfully
    if "scipy.sparse.linalg._propack" in sys.modules:
        _SCIPY_PATCHED = True
        return

    class MockPropackModule(types.ModuleType):
        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    mock_propack = MockPropackModule("scipy.sparse.linalg._propack")
    mock_propack._spropack = MockPropackModule("_spropack")
    mock_propack._dpropack = MockPropackModule("_dpropack")
    mock_propack._cpropack = MockPropackModule("_cpropack")
    mock_propack._zpropack = MockPropackModule("_zpropack")

    sys.modules["scipy.sparse.linalg._propack"] = mock_propack
    _SCIPY_PATCHED = True
