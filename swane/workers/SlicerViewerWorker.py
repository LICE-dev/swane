from swane.utils.qt_compat import QRunnable
import os
import subprocess


class SlicerViewerWorker(QRunnable):
    """
    Spawn a thread to open the workflow results scene into 3D Slicer.

    """

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
        # Just opens the scene; the automatic MELODIC resting-state
        # timecourse viewer is wired up by the SWANe slicerrc bootstrap
        # (see SlicerCheckWorker), so it also works when the user opens the
        # scene manually, outside SWANe.
        cmd = self.slicer_path + " " + self.scene_path
        # Discard stdout instead of piping it: nobody drains the pipe here, so a
        # PIPE would fill its OS buffer and deadlock Slicer once it prints enough.
        subprocess.Popen(
            cmd,
            cwd=os.getcwd(),
            shell=True,
            stdout=subprocess.DEVNULL,
            universal_newlines=True,
        )
