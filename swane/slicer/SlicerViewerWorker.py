from PySide6.QtCore import QRunnable, Signal, QObject
import os
import subprocess


class SlicerViewerWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer result export 

    """
    
    PROGRESS_MSG_PREFIX = 'SLICERLOADER: '
    END_MSG = "ENDLOADING"

    def __init__(self, slicer_path, scene_path, parent=None):
        super(SlicerViewerWorker, self).__init__(parent)
        self.slicer_path = slicer_path
        self.scene_path = scene_path

    def run(self):

        cmd = self.slicer_path + " --python-code 'slicer.util.loadScene(\"" + self.scene_path + "\")'"

        popen = subprocess.Popen(cmd, cwd=os.getcwd(), shell=True, stdout=subprocess.PIPE, universal_newlines=True)