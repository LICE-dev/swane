from PySide6.QtCore import QRunnable, Signal, QObject
import os
import subprocess

from swane.config.ConfigManager import ConfigManager
from swane.utils.DataInputList import DataInputList


class SlicerExportSignaler(QObject):
    export = Signal(str)


class SlicerExportWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer result export

    """

    PROGRESS_MSG_PREFIX = "SLICERLOADER: "
    END_MSG = "ENDLOADING"

    def __init__(
        self, slicer_path: str, result_dir: str, scene_ext: str, config: ConfigManager
    ):
        super(SlicerExportWorker, self).__init__()
        self.signal = SlicerExportSignaler()
        self.slicer_path: str = slicer_path
        self.result_dir: str = result_dir
        self.scene_ext: str = scene_ext
        self.config: ConfigManager = config

    def run(self):

        vein_threshold = self.config.getfloat_safe(
            DataInputList.VENOUS, "vein_segment_threshold"
        )
        dti_threshold = self.config.getfloat_safe(
            DataInputList.DTI, "tractography_threshold"
        )

        cmd = (
            self.slicer_path
            + " --no-splash --no-main-window --python-script "
            + os.path.join(
                os.path.dirname(__file__),
                f"slicer_script_result.py {self.scene_ext} {str(dti_threshold)} {str(vein_threshold)}",
            )
        )

        popen = subprocess.Popen(
            cmd,
            cwd=self.result_dir,
            shell=True,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        for stdout_line in iter(popen.stdout.readline, ""):
            if stdout_line.startswith(self.PROGRESS_MSG_PREFIX):
                self.signal.export.emit(
                    stdout_line.replace(self.PROGRESS_MSG_PREFIX, "").replace("\n", "")
                )
        popen.stdout.close()
        popen.wait()
        self.signal.export.emit(self.END_MSG)
