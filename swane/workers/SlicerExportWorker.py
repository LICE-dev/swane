from swane.utils.qt_compat import QRunnable, Signal, QObject
import logging
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

        vein_threshold_mr = self.config.getfloat_safe(
            DataInputList.VENOUS_MR, "vein_segment_threshold"
        )
        vein_threshold_ct = self.config.getfloat_safe(
            DataInputList.VENOUS_CT, "vein_segment_threshold"
        )
        dti_threshold = self.config.getfloat_safe(
            DataInputList.DTI, "tractography_threshold"
        )

        # Run without a shell: the script path is a separate argv element, so an
        # install dir containing spaces survives.
        result_script = os.path.join(
            os.path.dirname(__file__), "slicer_script_result.py"
        )
        cmd = [
            self.slicer_path,
            "--no-splash",
            "--no-main-window",
            "--python-script",
            result_script,
            "--dti_threshold",
            str(dti_threshold),
            "--vein_threshold_mr",
            str(vein_threshold_mr),
            "--vein_threshold_ct",
            str(vein_threshold_ct),
        ]

        popen = None
        try:
            popen = subprocess.Popen(
                cmd,
                cwd=self.result_dir,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            )
            for stdout_line in iter(popen.stdout.readline, ""):
                if stdout_line.startswith(self.PROGRESS_MSG_PREFIX):
                    self.signal.export.emit(
                        stdout_line.replace(self.PROGRESS_MSG_PREFIX, "").replace(
                            "\n", ""
                        )
                    )
            popen.stdout.close()
            popen.wait()
        except OSError as e:
            # Missing/stale Slicer path or permission problem: report it, but
            # never leave the modal progress dialog waiting for END_MSG.
            logging.getLogger(__name__).error(
                "3D Slicer export failed to run %s: %s", self.slicer_path, e
            )
        finally:
            if popen is not None and popen.poll() is None:
                # an exception interrupted the read loop: do not leak Slicer
                popen.kill()
                popen.wait()
            self.signal.export.emit(self.END_MSG)
