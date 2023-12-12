from PySide6.QtCore import QRunnable
import os
import subprocess
from PySide6.QtCore import QThreadPool

class SlicerViewerWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer result export 

    """
    
    PROGRESS_MSG_PREFIX = 'SLICERLOADER: '
    END_MSG = "ENDLOADING"

    def __init__(self, slicer_path, scene_path):
        super(SlicerViewerWorker, self).__init__()
        self.slicer_path = slicer_path
        self.scene_path = scene_path

    def run(self):

        cmd = self.slicer_path + " --python-code 'slicer.util.loadScene(\"" + self.scene_path + "\")'"

        popen = subprocess.Popen(cmd, cwd=os.getcwd(), shell=True, stdout=subprocess.PIPE, universal_newlines=True)


def load_scene(slicer_path: str, scene_path: str):
    """
    Visualize the workflow results into 3D Slicer.

    Returns
    -------
    None.

    """
    if os.path.exists(scene_path):
        slicer_open_thread = SlicerViewerWorker(slicer_path, scene_path)
        QThreadPool.globalInstance().start(slicer_open_thread)
