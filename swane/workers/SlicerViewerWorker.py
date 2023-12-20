from PySide6.QtCore import QRunnable
import os
import subprocess

class SlicerViewerWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer result export 

    """
    
    PROGRESS_MSG_PREFIX = 'SLICERLOADER: '
    END_MSG = "ENDLOADING"

    def __init__(self, slicer_path: str, scene_path: str):
        """
            Visualize the workflow results into 3D Slicer.

        Parameters
        -------
        slicer_path: str
           The slicer execution path
        scene_path: str
           The scene file path

        """
        super(SlicerViewerWorker, self).__init__()
        self.slicer_path: str = slicer_path
        self.scene_path: str = scene_path

    def run(self):
        cmd = self.slicer_path + " --python-code 'slicer.util.loadScene(\"" + self.scene_path + "\")'"
        popen = subprocess.Popen(cmd, cwd=os.getcwd(), shell=True, stdout=subprocess.PIPE, universal_newlines=True)
