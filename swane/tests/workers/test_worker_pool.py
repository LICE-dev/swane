import gc
import threading
import weakref

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip("requires a working PySide6", allow_module_level=True)

from PySide6.QtCore import QEventLoop, QObject, QRunnable, Signal

from swane.workers import worker_pool
from swane.workers.LicenseResolveWorker import LicenseResolveWorker
from swane.workers.worker_pool import start_worker


def _wait_released(qtbot):
    qtbot.waitUntil(lambda: len(worker_pool._active) == 0, timeout=10000)
    gc.collect()


class _RecordingSignal(QObject):
    done = Signal()

    def __init__(self, deaths):
        super().__init__()
        self._deaths = deaths

    def __del__(self):
        self._deaths.append(("signal", threading.current_thread()))


class _RecordingWorker(QRunnable):
    def __init__(self, deaths, fail):
        super().__init__()
        self._deaths = deaths
        self.fail = fail
        self.signal = _RecordingSignal(deaths)

    def __del__(self):
        self._deaths.append(("worker", threading.current_thread()))

    def run(self):
        if self.fail:
            raise RuntimeError("synthetic worker failure")
        self.signal.done.emit()


def test_workers_released_on_gui_thread_without_leak(qtbot):
    # A runnable handed to QThreadPool.start is destroyed on the pool thread
    # (autoDelete) or leaked (no autoDelete). start_worker must free every
    # worker, and the GUI-thread QObject it holds, on the GUI thread only.
    deaths = []
    refs = []
    for i in range(50):
        worker = _RecordingWorker(deaths, fail=(i % 10 == 0))
        refs.append((weakref.ref(worker), weakref.ref(worker.signal)))
        start_worker(worker)
        del worker

    _wait_released(qtbot)

    assert all(w() is None and s() is None for w, s in refs), "leaked workers"
    assert len(deaths) == 100
    off_gui = [kind for kind, thread in deaths if thread is not threading.main_thread()]
    assert off_gui == [], "workers destroyed off the GUI thread"


def test_license_resolve_finished_path_stress(qtbot):
    # MainWindow's license gate: ``finished`` is emitted in run()'s finally and
    # quits the local loop, after which the GUI drops every worker reference
    # while the pool thread is still returning from run().
    refs = []
    for _ in range(100):
        loop = QEventLoop()
        delivery_threads = []
        worker = LicenseResolveWorker([], {})
        worker.signal.resolved.connect(
            lambda _res: delivery_threads.append(threading.current_thread())
        )
        worker.signal.finished.connect(loop.quit)
        refs.append(weakref.ref(worker))
        start_worker(worker)
        loop.exec()
        del worker
        assert delivery_threads == [threading.main_thread()]

    _wait_released(qtbot)
    assert all(r() is None for r in refs), "leaked LicenseResolveWorker"


def test_headless_fallback_runs_synchronously(monkeypatch):
    monkeypatch.setattr(worker_pool, "QT_AVAILABLE", False)
    calls = []

    class _Worker:
        def run(self):
            calls.append(threading.current_thread())

    start_worker(_Worker())
    assert calls == [threading.main_thread()]
    assert worker_pool._active == {}
