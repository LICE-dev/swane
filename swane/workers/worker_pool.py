import itertools
import threading
import traceback

from swane.utils.qt_compat import QT_AVAILABLE, QObject, QThreadPool, Signal

if QT_AVAILABLE:
    from PySide6.QtCore import QCoreApplication, Slot

# Workers currently queued or running, keyed by a launch token. Holding them
# here (not in Qt) keeps a single owner for every worker: the Python refcount.
_active = {}
_lock = threading.Lock()
_keys = itertools.count()
_releaser = None

if QT_AVAILABLE:

    class _WorkerReleaser(QObject):
        """GUI-thread object that drops the last reference to finished workers."""

        release = Signal(object)

        def __init__(self):
            super().__init__()
            self.release.connect(self._on_release)

        @Slot(object)
        def _on_release(self, key):
            with _lock:
                _active.pop(key, None)


def start_worker(worker):
    """
    Run a SWANe worker on the global QThreadPool with a GUI-thread lifetime.

    Handing a Python QRunnable to ``QThreadPool.start`` gives its ownership to
    Qt: with autoDelete (the default) Qt destroys it, and the GUI-thread signal
    QObject it holds, on the pool thread while Python may still reference it,
    corrupting the heap; without autoDelete PySide never releases it, leaking
    the worker. The pool receives a plain callable instead, the worker stays
    referenced here, and its last reference is dropped on the GUI thread once
    run() has fully returned.

    Must be called from the GUI thread.

    Parameters
    ----------
    worker:
        Any object exposing ``run()``, typically a ``swane.workers`` QRunnable.
    """
    if not QT_AVAILABLE:
        # Headless fallback: run synchronously, as qt_compat's pool does.
        try:
            worker.run()
        except Exception:
            traceback.print_exc()
        return

    global _releaser
    if _releaser is None:
        _releaser = _WorkerReleaser()
        app = QCoreApplication.instance()
        if app is not None:
            _releaser.moveToThread(app.thread())

    key = next(_keys)
    with _lock:
        _active[key] = worker

    def _run():
        with _lock:
            running = _active[key]
        try:
            running.run()
        except Exception:
            traceback.print_exc()
        finally:
            # Drop this thread's reference before asking the GUI thread to
            # release the worker, so its destruction can only happen there.
            del running
            _releaser.release.emit(key)

    QThreadPool.globalInstance().start(_run)
