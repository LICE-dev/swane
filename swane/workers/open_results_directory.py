import subprocess
from sys import platform
import os


def open_results_directory(pushed: bool, results_dir: str):
    """
    Open the result directory in the file explorer
    Parameters
    ----------
    pushed: bool
        Unused, passed by QPushButton
    results_dir: str
        The path to show in file explorer
    """
    if platform == 'win32':
        os.startfile(results_dir)
    elif platform == 'darwin':
        subprocess.Popen(['open', results_dir])

    else:
        try:
            subprocess.Popen(['xdg-open', results_dir])
        except OSError:
            pass

