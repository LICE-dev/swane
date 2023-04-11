from PySide6.QtCore import QRunnable, Signal, QObject
import os
import subprocess


class SlicerExportSignaler(QObject):
    export = Signal(str)


class SlicerExportWorker(QRunnable):
    PROGRESS_MSG_PREFIX = 'SLICERLOADER: '
    END_MSG = "ENDLOADING"

    def __init__(self, slicer_path, pt_folder, scene_ext, parent=None):
        super(SlicerExportWorker, self).__init__(parent)
        self.signal = SlicerExportSignaler()
        self.slicer_path = slicer_path
        self.pt_folder = pt_folder
        self.scene_ext = scene_ext

    def run(self):

        cmd = self.slicer_path + " --no-splash --no-main-window --python-script " + os.path.join(
            os.path.dirname(__file__), "slicer_script_result.py " + self.scene_ext)

        popen = subprocess.Popen(cmd, cwd=self.pt_folder, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
        for stdout_line in iter(popen.stdout.readline, ""):
            print(stdout_line)
            if stdout_line.startswith(self.PROGRESS_MSG_PREFIX):
                self.signal.export.emit(stdout_line.replace(self.PROGRESS_MSG_PREFIX, '').replace('\n', ''))
        popen.stdout.close()
        popen.wait()
        self.signal.export.emit(self.END_MSG)
