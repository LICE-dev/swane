"""Compatibility layer for importing PySide6 Qt classes in tests.

Provides lightweight fallbacks when PySide6 is unavailable or fails to import
(e.g. in CI or constrained environments). Tests and non-GUI code should use
these symbols instead of importing PySide6 directly.

Some platforms don't raise a catchable ``ImportError`` when PySide6 is broken:
the shiboken6/PySide6 extension *natively* crashes the interpreter on import
(observed as a stack-buffer overrun on certain Windows/Python builds). A plain
``try/except`` cannot guard a native crash, so — only under pytest, where we
want graceful degradation to headless stubs instead of a dead test process — we
first probe the import in a throwaway subprocess. If that probe crashes or
errors, we use the pure-Python fallbacks and the whole unit-test suite stays
runnable on any environment. The real application keeps the direct import: if Qt
is genuinely broken the GUI can't run anyway.
"""

import os
import subprocess
import sys


def _pyside6_imports_cleanly() -> bool:
    """Return True iff ``import PySide6.QtCore`` succeeds in a child process.

    Run in a subprocess so a *native* crash there cannot take down this process.
    """
    try:
        return (
            subprocess.run(
                [sys.executable, "-c", "import PySide6.QtCore"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            ).returncode
            == 0
        )
    except Exception:
        return False


# Under pytest we cannot afford a native crash while importing PySide6, so gate
# the real import behind the subprocess probe. Outside pytest (the real app) we
# import PySide6 directly and unconditionally.
_under_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
_use_real_qt = (not _under_pytest) or _pyside6_imports_cleanly()

if _use_real_qt:
    try:
        from PySide6.QtCore import Signal, QObject, QRunnable, QThreadPool
    except Exception:
        _use_real_qt = False

if not _use_real_qt:
    # Lightweight, headless fallback implementations.
    class Signal:
        def __init__(self, *args, **kwargs):
            self._slots = []

        def connect(self, fn):
            self._slots.append(fn)

        def emit(self, *args, **kwargs):
            for fn in list(self._slots):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    # swallow exceptions from test callbacks
                    pass

    class QObject:
        pass

    class QRunnable:
        pass

    class _QThreadPoolGlobal:
        def start(self, runnable):
            # run synchronously to keep tests deterministic
            try:
                runnable.run()
            except Exception:
                pass

    class QThreadPool:
        @staticmethod
        def globalInstance():
            return _QThreadPoolGlobal()


# True when the real Qt binding is in use, False when the headless fallbacks
# above are active (PySide6 missing or crashing). Tests can gate GUI-only
# fixtures/tests on this so they skip with a clear reason instead of erroring.
QT_AVAILABLE = _use_real_qt

# Export names
__all__ = ["Signal", "QObject", "QRunnable", "QThreadPool", "QT_AVAILABLE"]
