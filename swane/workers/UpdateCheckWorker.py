from PySide6.QtCore import QRunnable, Signal, QObject
from packaging import version
import subprocess
import sys
from swane import __version__
import re


class UpdateCheckSignaler(QObject):
    last_available = Signal(str)


class UpdateCheckWorker(QRunnable):
    """
    Spawn a thread to check swane updates on pip

    """

    def __init__(self):
        super(UpdateCheckWorker, self).__init__()
        self.signal: UpdateCheckSignaler = UpdateCheckSignaler()

    def run(self):
        cmd = sys.executable + " -m pip index versions swane 2>/dev/null"
        output = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
        for stdout_line in output.split("\n"):
            regex_pattern = r'^swane \((.+)\)$'
            match = re.match(regex_pattern, stdout_line)
            if match:
                pip_version = match.group(1)
                if UpdateCheckWorker.is_newer_version(pip_version):
                    self.signal.last_available.emit(pip_version)
                    break

    @staticmethod
    def is_newer_version(pip_version: str) -> bool:
        """
            Compare current version with pip version

        Parameters
        ----------
        pip_version : str
            The version retrieved from pip

        Returns
        -------
            True if pip version is newer than current version
        """

        try:
            if version.parse(pip_version) > version.parse(__version__):
                return True
        except:
            pass
        return False

