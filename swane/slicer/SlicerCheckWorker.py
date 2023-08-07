import os
import subprocess
from PySide6.QtCore import QRunnable, Signal, QObject
from swane import strings


class SlicerCheckSignaler(QObject):
    slicer = Signal(str, str, bool)


class SlicerCheckWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer dependency check 

    """
    
    def __init__(self, current_slicer_path, parent=None):
        super(SlicerCheckWorker, self).__init__(parent)
        self.signal = SlicerCheckSignaler()
        self.current_slicer_path = current_slicer_path

    def run(self):

        repeat = True

        while repeat:
            if not os.path.exists(self.current_slicer_path):
                self.current_slicer_path = ''
            elif os.path.isfile(self.current_slicer_path):
                self.current_slicer_path = os.path.dirname(self.current_slicer_path)

            import platform
            if platform.system() == "Darwin":
                if self.current_slicer_path == '':
                    src_path = "/Applications"
                else:
                    src_path = self.current_slicer_path
                find_cmd = "find " + src_path + " -type f -wholename *app/Contents/bin/PythonSlicer -print 2>/dev/null"
                rel_path = "../MacOS/Slicer"
            else:
                if self.current_slicer_path == '':
                    src_path = "/"
                else:
                    src_path = self.current_slicer_path
                find_cmd = "find " + src_path + " -executable -type f -wholename *bin/PythonSlicer -print -quit 2>/dev/null"
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
                if self.current_slicer_path != '':
                    self.current_slicer_path = ''
                else:
                    repeat = False
                msg = strings.check_dep_slicer_error1
            else:
                repeat = False
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
