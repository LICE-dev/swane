"""Shared fixtures for the head-less UI tests.

These tests need a real Qt binding. When PySide6 is unavailable or broken (e.g.
the Store-packaged Python where shiboken6 crashes on import), this conftest must
NOT import PySide6 — doing so would crash the whole pytest session before any
test can be skipped. The imports and fixtures below are therefore guarded on
``QT_AVAILABLE``; each GUI test module additionally skips itself with a clear
reason at module load, so the suite stays runnable everywhere.
"""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if QT_AVAILABLE:
    from PySide6.QtCore import QRunnable, QObject, Signal

    import swane.ui.MainWindow as main_window_mod
    from swane.ui.MainWindow import MainWindow

    class _DummySignal(QObject):
        last_available = Signal(str)

    class _DummyUpdateWorker(QRunnable):
        """No-op replacement for UpdateCheckWorker (no pip/network call)."""

        def __init__(self):
            super().__init__()
            self.signal = _DummySignal()

        def run(self):
            pass

    @pytest.fixture
    def offline_update(monkeypatch):
        """Stop MainWindow from spawning the real update checker and Slicer check.

        Both run on the global ``QThreadPool``: ``UpdateCheckWorker`` hits the
        network, and ``check_slicer`` launches the real Slicer executable when
        one is installed, leaving a thread blocked on the subprocess so the
        interpreter never exits. Neutralise both so head-less UI tests terminate
        cleanly.
        """
        monkeypatch.setattr(main_window_mod, "UpdateCheckWorker", _DummyUpdateWorker)
        monkeypatch.setattr(
            "swane.utils.DependencyManager.DependencyManager.check_slicer",
            staticmethod(lambda *args, **kwargs: None),
        )

    @pytest.fixture
    def main_window(qtbot, global_config, offline_update):
        """A constructed, offline MainWindow registered with qtbot."""
        window = MainWindow(global_config)
        qtbot.addWidget(window)
        return window
