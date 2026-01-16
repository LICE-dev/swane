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

    BEGIN_MARKER = "# === BEGIN HIDEZERO PATCH ==="
    END_MARKER = "# === END HIDEZERO PATCH ==="
    HIDE_ZERO_CODE = f"""{BEGIN_MARKER}
def apply_hide_zero(node):
    if not node or not node.IsA("vtkMRMLScalarVolumeNode"):
        return
    if node.GetAttribute("HideZero") != "True":
        return
    dn = node.GetDisplayNode()
    if not dn:
        return
    dn.SetApplyThreshold(True)
    dn.SetLowerThreshold(1e-6)
    dn.SetUpperThreshold(float("inf"))
    dn.SetAutoWindowLevel(False)

def apply_hide_zero_to_all():
    for node in slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode"):
        apply_hide_zero(node)

def on_scene_imported(caller, event):
    apply_hide_zero_to_all()

if not hasattr(slicer, "_hideZeroInstalled"):
    slicer._hideZeroInstalled = True
    slicer.mrmlScene.AddObserver(
        slicer.mrmlScene.EndImportEvent,
        on_scene_imported
    )
    apply_hide_zero_to_all()
{END_MARKER}
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
            current_slicer_path = ""
        elif os.path.isfile(current_slicer_path):
            current_slicer_path = os.path.dirname(current_slicer_path)

        # Adjust search path based on OS
        if platform.system() == "Darwin":
            if current_slicer_path == "":
                src_path = "/Applications"
            else:
                src_path = current_slicer_path
            find_cmd = (
                "find "
                + src_path
                + " -type f -wholename *app/Contents/bin/PythonSlicer -print -quit 2>/dev/null"
            )
            rel_path = "../MacOS/Slicer"
        else:
            if current_slicer_path == "":
                src_path = "/"
            else:
                src_path = current_slicer_path
            find_cmd = (
                "find "
                + src_path
                + " -executable -type f -wholename *bin/PythonSlicer -print -quit 2>/dev/null"
            )

            rel_path = "../Slicer"

        # Perform search with find
        output = subprocess.run(
            find_cmd, shell=True, stdout=subprocess.PIPE
        ).stdout.decode("utf-8")
        split = output.split("\n")
        while "" in split:
            split.remove("")
        return split, rel_path

    @staticmethod
    def read_slicerrc(slicerrc_path):
        if os.path.exists(slicerrc_path):
            with open(slicerrc_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    @staticmethod
    def write_slicerrc(slicerrc_path, content):
        with open(slicerrc_path, "w", encoding="utf-8") as f:
            f.write(content)

    # -------------------------
    # Check if patch exists and matches
    # -------------------------
    @staticmethod
    def check_patch(slicerrc_path):
        """Return True if the HideZero patch exists and is identical to our snippet."""
        content = SlicerCheckWorker.read_slicerrc(slicerrc_path)
        if SlicerCheckWorker.BEGIN_MARKER in content and SlicerCheckWorker.END_MARKER in content:
            start = content.index(SlicerCheckWorker.BEGIN_MARKER)
            end = content.index(SlicerCheckWorker.END_MARKER) + len(SlicerCheckWorker.END_MARKER)
            current_patch = content[start:end]
            return current_patch.strip() == SlicerCheckWorker.HIDE_ZERO_CODE.strip()
        return False

    # -------------------------
    # Add or replace patch
    # -------------------------
    @staticmethod
    def add_slicer_startup_patch():
        """Add the HideZero patch to slicerrc.py. Replaces old patch if different."""
        slicerrc_path = os.path.expanduser("~/.slicerrc.py")

        if SlicerCheckWorker.check_patch(slicerrc_path):
            return

        # Remove old patch if exists
        content = SlicerCheckWorker.remove_patch(slicerrc_path, return_content=True)

        # Ensure trailing newline
        if content and not content.endswith("\n"):
            content += "\n"

        # Append the new patch
        content += SlicerCheckWorker.HIDE_ZERO_CODE + "\n"
        SlicerCheckWorker.write_slicerrc(slicerrc_path, content)

    # -------------------------
    # Remove patch
    # -------------------------
    @staticmethod
    def remove_patch(slicerrc_path, return_content=False):
        """Remove the HideZero patch from slicerrc.py."""
        content = SlicerCheckWorker.read_slicerrc(slicerrc_path)
        if SlicerCheckWorker.BEGIN_MARKER in content and SlicerCheckWorker.END_MARKER in content:
            start = content.index(SlicerCheckWorker.BEGIN_MARKER)
            end = content.index(SlicerCheckWorker.END_MARKER) + len(SlicerCheckWorker.END_MARKER)
            new_content = content[:start] + content[end:]
            if return_content:
                return new_content
            SlicerCheckWorker.write_slicerrc(slicerrc_path, new_content)
        elif return_content:
            return content


    def run(self):
        repeat = True
        cmd = ""
        state: DependenceStatus = DependenceStatus.MISSING
        label = ""
        slicer_version = ""

        while repeat:
            split, rel_path = SlicerCheckWorker.find_slicer_python(
                self.current_slicer_path
            )
            # find slicerpython executable and go back to slicer executable with rel_path
            for entry in split:
                cmd = os.path.abspath(os.path.join(os.path.dirname(entry), rel_path))
                break
            if cmd == "" or not os.path.exists(cmd):
                # if slicer executable is not found, search entire filesystem if we were searchng a specific folder
                # otherwise stop loop, slicer is not detectable on system
                if self.current_slicer_path != "":
                    self.current_slicer_path = ""
                else:
                    repeat = False
                label = strings.check_dep_slicer_error1
            else:
                # if slicer command is found, version check
                repeat = False
                cmd2 = cmd + " --version"
                output2 = subprocess.run(
                    cmd2, shell=True, stdout=subprocess.PIPE
                ).stdout.decode("utf-8")
                slicer_version = output2.replace("Slicer ", "").replace("\n", "")
                if not DependencyManager.check_slicer_version(slicer_version):
                    label = strings.check_dep_slicer_wrong_version % (
                        slicer_version,
                        DependencyManager.MIN_SLICER_VERSION,
                    )
                    state = DependenceStatus.WARNING
                else:
                    # Try to automatically install Slicer extensions
                    cmd3 = (
                        cmd
                        + " --no-splash --no-main-window --python-script "
                        + os.path.join(
                            os.path.dirname(__file__),
                            "slicer_script_module_install.py ",
                        )
                        + ','.join(DependencyManager.SLICER_MODULES)
                    )
                    output3 = subprocess.run(
                        cmd3, shell=True, stdout=subprocess.PIPE
                    ).stdout.decode("utf-8")
                    if "MODULE FOUND" in output3:
                        state = DependenceStatus.DETECTED
                        label = strings.check_dep_slicer_found % slicer_version
                        SlicerCheckWorker.add_slicer_startup_patch()
                    else:
                        missing_modules = ', '.join(DependencyManager.SLICER_MODULES)
                        for line in output3.splitlines():
                            if "MODULE MISSING:" in line:
                                missing_modules = line.split("MODULE MISSING:", 1)[1].strip()
                                break
                        state = DependenceStatus.WARNING
                        label = strings.check_dep_slicer_error2 % missing_modules

        self.signal.slicer.emit(cmd, slicer_version, label, state)

    def terminate(self):
        return
