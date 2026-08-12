"""Shared fixtures for the head-less UI tests."""

import pytest
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
    """Stop MainWindow from spawning the real (network) update checker."""
    monkeypatch.setattr(main_window_mod, "UpdateCheckWorker", _DummyUpdateWorker)


@pytest.fixture
def main_window(qtbot, global_config, offline_update):
    """A constructed, offline MainWindow registered with qtbot."""
    window = MainWindow(global_config)
    qtbot.addWidget(window)
    return window
