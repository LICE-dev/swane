# -*- coding: utf-8 -*-
"""Monkeypatch for SciPy on macOS to bypass the _spropack zero-fill section bug."""

import sys
import types

_SCIPY_PATCHED = False


def apply_scipy_patches():
    """
    Install a mock for scipy.sparse.linalg._propack to avoid a crash on macOS.
    
    Because antspyx < 0.6.4 strictly requires scipy < 1.16, pip forces the installation
    of older scipy wheels. These older wheels contain broken binary modules
    (_spropack.cpython-312-darwin.so, etc.) that cause an immediate ImportError: dlopen
    crash with a "__DATA/__thread_bss has a zero-fill section type" error on recent
    macOS versions (like Sequoia or with recent toolchains).
    
    Since SWANe and Nipype never actually use the 'propack' SVD solver, we can bypass
    this crash entirely by injecting a dummy module into sys.modules BEFORE scipy
    is fully imported.
    """
    global _SCIPY_PATCHED
    if _SCIPY_PATCHED:
        return

    if sys.platform != "darwin":
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
