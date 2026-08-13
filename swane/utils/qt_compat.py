"""Compatibility layer for importing PySide6 Qt classes in tests.

Provides lightweight fallbacks when PySide6 is unavailable or fails to import
(e.g., in CI or constrained environments). Tests and non-GUI code should use
these symbols instead of importing PySide6 directly.
"""

try:
    from PySide6.QtCore import Signal, QObject, QRunnable, QThreadPool

except Exception:
    # Lightweight falling-back implementations
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


# Export names
__all__ = ["Signal", "QObject", "QRunnable", "QThreadPool"]
