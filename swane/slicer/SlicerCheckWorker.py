import os
import subprocess
from PySide6.QtCore import QRunnable, Signal, QObject
from swane import strings


class SlicerCheckSignaler(QObject):
    slicer = Signal(str, str, bool)


class SlicerCheckWorker(QRunnable):
    def __init__(self, parent=None):
        super(SlicerCheckWorker, self).__init__(parent)
        self.signal = SlicerCheckSignaler()

    def run(self):
        import platform
        if platform.system() == "Darwin":
            find_cmd = "find /Applications -type f -wholename *app/Contents/bin/PythonSlicer -print 2>/dev/null"
            rel_path = "../MacOS/Slicer"
        else:
            find_cmd = "find / -executable -type f -wholename *bin/PythonSlicer -print -quit 2>/dev/null"
            rel_path = "../Slicer"
        output = subprocess.run(find_cmd, shell=True,
                                stdout=subprocess.PIPE).stdout.decode('utf-8')
        split = output.split("\n")
        cmd = ''
        found = False
        for entry in split:
            if entry == '':
                continue
            cmd = os.path.abspath(os.path.join(
                os.path.dirname(entry), rel_path))
            break
        if cmd == '' or not os.path.exists(cmd):
            msg = strings.check_dep_slicer_error1
        else:
            cmd2 = cmd + " --no-splash --no-main-window --python-script " + \
                   os.path.join(os.path.dirname(__file__), "slicer_script_freesurfer_module_check.py")
            output2 = subprocess.run(
                cmd2, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
            if 'MODULE FOUND' in output2:
                found = True
                msg = strings.check_dep_slicer_found
            else:
                msg = strings.check_dep_slicer_error2

        self.signal.slicer.emit(cmd, msg, found)

    def terminate(self):
        return
