from swane.utils.qt_compat import QRunnable, Signal, QObject
import os
import shlex
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

        vein_threshold_mr = self.config.getfloat_safe(
            DataInputList.VENOUS_MR, "vein_segment_threshold"
        )
        vein_threshold_ct = self.config.getfloat_safe(
            DataInputList.VENOUS_CT, "vein_segment_threshold"
        )
        dti_threshold = self.config.getfloat_safe(
            DataInputList.DTI, "tractography_threshold"
        )

        # Keep the script path quoted and separate from its arguments so an
        # install dir containing spaces does not break the shell word-splitting.
        result_script = os.path.join(
            os.path.dirname(__file__), "slicer_script_result.py"
        )
        cmd = (
            self.slicer_path
            + " --no-splash --no-main-window --python-script "
            + shlex.quote(result_script)
            + f" --dti_threshold {str(dti_threshold)}"
            + f" --vein_threshold_mr {str(vein_threshold_mr)}"
            + f" --vein_threshold_ct {str(vein_threshold_ct)}"
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
