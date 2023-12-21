import os
import subprocess
from PySide6.QtCore import QRunnable, Signal, QObject
from swane import strings
from swane.utils.DependencyManager import DependencyManager, DependenceStatus
import platform


class SlicerCheckSignaler(QObject):
    slicer = Signal(str, str, str, DependenceStatus)


class SlicerCheckWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer dependency check 

    """
    
    def __init__(self, current_slicer_path: str):
        super(SlicerCheckWorker, self).__init__()
        self.signal = SlicerCheckSignaler()
        self.current_slicer_path = current_slicer_path

    @staticmethod
    def find_slicer_python(current_slicer_path: str) -> (list[str], str):
        # If current_slicer_path doeas not exists, replace with a blank string
        # If it is a file, search in its directory
        if not os.path.exists(current_slicer_path):
            current_slicer_path = ''
        elif os.path.isfile(current_slicer_path):
            current_slicer_path = os.path.dirname(current_slicer_path)

        # Adjust search path based on OS
        if platform.system() == "Darwin":
            if current_slicer_path == '':
                src_path = "/Applications"
            else:
                src_path = current_slicer_path
            find_cmd = "find " + src_path + " -type f -wholename *app/Contents/bin/PythonSlicer -print -quit 2>/dev/null"
            rel_path = "../MacOS/Slicer"
        else:
            if current_slicer_path == '':
                src_path = "/"
            else:
                src_path = current_slicer_path
            find_cmd = "find " + src_path + " -executable -type f -wholename *bin/PythonSlicer -print -quit 2>/dev/null"
            rel_path = "../Slicer"

        # Perform search with find
        output = subprocess.run(find_cmd, shell=True,
                                stdout=subprocess.PIPE).stdout.decode('utf-8')
        split = output.split("\n")
        while "" in split:
            split.remove("")
        return split, rel_path

    def run(self):
        repeat = True
        cmd = ""
        state: DependenceStatus = DependenceStatus.MISSING
        label = ""
        slicer_version = ""

        while repeat:
            split, rel_path = SlicerCheckWorker.find_slicer_python(self.current_slicer_path)
            # find slicerpython executable and go back to slicer executable with rel_path
            for entry in split:
                cmd = os.path.abspath(os.path.join(
                    os.path.dirname(entry), rel_path))
                break
            if cmd == '' or not os.path.exists(cmd):
                # if slicer executable is not found, search entire filesystem if we were searchng a specific folder
                # otherwise stop loop, slicer is not detectable on system
                if self.current_slicer_path != '':
                    self.current_slicer_path = ''
                else:
                    repeat = False
                label = strings.check_dep_slicer_error1
            else:
                # if slicer command is found, version check
                repeat = False
                cmd2 = cmd + " --version"
                output2 = subprocess.run(
                    cmd2, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
                slicer_version = output2.replace("Slicer ", "").replace("\n", "")
                if not DependencyManager.check_slicer_version(slicer_version):
                    label = strings.check_dep_slicer_wrong_version % (slicer_version, DependencyManager.MIN_SLICER_VERSION)
                    state = DependenceStatus.WARNING
                else:
                    # if version check is passed, check for freesurfer module
                    # TODO: we can try to install missing feesurfer module automatically.
                    #   see slicer_script_freesurfer_module_install.py for example
                    cmd3 = cmd + " --no-splash --no-main-window --python-script " + \
                           os.path.join(os.path.dirname(__file__), "slicer_script_freesurfer_module_check.py")
                    output3 = subprocess.run(
                        cmd3, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
                    if 'MODULE FOUND' in output3:
                        state = DependenceStatus.DETECTED
                        label = strings.check_dep_slicer_found % slicer_version
                    else:
                        label = strings.check_dep_slicer_error2

        self.signal.slicer.emit(cmd, slicer_version, label, state)

    def terminate(self):
        return
