from PySide6.QtCore import QRunnable, Signal, QObject
import os
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
        self.signal = UpdateCheckSignaler()

    def run(self):
        cmd = sys.executable + " -m pip index versions swane"
        output = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
        for stdout_line in output.split("\n"):
            regex_pattern = "^swane \((.+)\)$"
            match = re.match(regex_pattern, stdout_line)
            if match:
                self.signal.last_available.emit(match.group(1))

