from swane.utils.qt_compat import QRunnable, Signal, QObject
from swane.utils.LicenseReference import LICENSES
from swane.utils.license_consent import resolve_license_text


class LicenseResolveSignaler(QObject):
    resolved = Signal(list)


class LicenseResolveWorker(QRunnable):
    """
    Resolve external tool license texts off the GUI thread.

    Resolution may read local files and, as a fallback, perform a bounded
    network fetch; running it here keeps the UI responsive instead of freezing
    the main thread while the license is downloaded.
    """

    def __init__(self, tool_ids, context, timeout: float = 8.0):
        super(LicenseResolveWorker, self).__init__()
        self.tool_ids = list(tool_ids)
        self.context = dict(context)
        self.timeout = timeout
        self.signal: LicenseResolveSignaler = LicenseResolveSignaler()

    def run(self):
        resolved = [
            resolve_license_text(LICENSES[tool_id], self.context, self.timeout)
            for tool_id in self.tool_ids
        ]
        self.signal.resolved.emit(resolved)
