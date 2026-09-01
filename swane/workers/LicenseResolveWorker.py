from concurrent.futures import ThreadPoolExecutor, as_completed

from swane.utils.qt_compat import QRunnable, Signal, QObject
from swane.utils.LicenseReference import LICENSES
from swane.utils.license_consent import (
    DEFAULT_LICENSE_FETCH_TIMEOUT,
    resolve_license_text,
)

MAX_LICENSE_RESOLVE_WORKERS = 5


class LicenseResolveSignaler(QObject):
    resolved = Signal(list)
    failed = Signal(str)
    finished = Signal()


class LicenseResolveWorker(QRunnable):
    """
    Resolve external tool license texts off the GUI thread.

    Resolution may read local files and, as a fallback, perform a bounded
    network fetch; running it here keeps the UI responsive instead of freezing
    the main thread while the license is downloaded.
    """

    def __init__(
        self, tool_ids, context, timeout: float = DEFAULT_LICENSE_FETCH_TIMEOUT
    ):
        super(LicenseResolveWorker, self).__init__()
        self.tool_ids = list(tool_ids)
        self.context = dict(context)
        self.timeout = timeout
        self.signal: LicenseResolveSignaler = LicenseResolveSignaler()

    def run(self):
        try:
            if not self.tool_ids:
                self.signal.resolved.emit([])
                return

            # At most five tools participate in the gate. Resolving all of them
            # concurrently turns the network wait into one bounded timeout
            # window instead of accumulating one timeout per missing local file.
            resolved = [None] * len(self.tool_ids)
            max_workers = min(MAX_LICENSE_RESOLVE_WORKERS, len(self.tool_ids))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        resolve_license_text,
                        LICENSES[tool_id],
                        self.context,
                        self.timeout,
                    ): index
                    for index, tool_id in enumerate(self.tool_ids)
                }
                for future in as_completed(futures):
                    resolved[futures[future]] = future.result()

            self.signal.resolved.emit(resolved)
        except Exception as exc:
            self.signal.failed.emit(str(exc))
        finally:
            self.signal.finished.emit()
