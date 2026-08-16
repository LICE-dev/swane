import os
import subprocess
from swane.utils.qt_compat import QRunnable, Signal, QObject
from swane import strings
from swane.utils.DependencyManager import DependencyManager, DependenceStatus
import platform


class SlicerCheckSignaler(QObject):
    slicer = Signal(str, str, str, DependenceStatus)


class SlicerCheckWorker(QRunnable):
    """
    Spawn a thread for 3D Slicer dependency check

    """

    BEGIN_MARKER = "# === BEGIN SWANE PATCH ==="
    END_MARKER = "# === END SWANE PATCH ==="
    # Older SWANe versions injected an inline hide-zero patch under these
    # markers. hide-zero is now handled entirely at scene-export time, so the
    # block is dead; clean it up on migration.
    LEGACY_MARKERS = [
        ("# === BEGIN HIDEZERO PATCH ===", "# === END HIDEZERO PATCH ==="),
    ]

    @staticmethod
    def build_startup_patch() -> str:
        """
        Build the SWANe startup stub for ``~/.slicerrc.py``.

        The stub is deliberately tiny and stable: it only adds SWANe's
        ``workers`` folder to ``sys.path`` and imports ``slicerrc_swane``,
        which holds the actual logic and ships with SWANe. That way future
        changes to SWANe's Slicer helpers take effect without rewriting the
        user's slicerrc, and any failure is swallowed so an unrelated Slicer
        session is never broken.

        Returns
        -------
        str
            The full marker-delimited patch text.
        """
        workers_dir = os.path.dirname(os.path.abspath(__file__))
        return f"""{SlicerCheckWorker.BEGIN_MARKER}
# Managed by SWANe. Bootstraps SWANe's Slicer helpers (e.g. the resting-state
# MELODIC timecourse viewer). Safe to delete; SWANe re-adds it on its next
# Slicer dependency check.
import os as _swane_os
import sys as _swane_sys

_swane_workers_dir = {workers_dir!r}
if _swane_os.path.isdir(_swane_workers_dir):
    if _swane_workers_dir not in _swane_sys.path:
        _swane_sys.path.insert(0, _swane_workers_dir)
    try:
        import slicerrc_swane as _swane_rc
    except Exception as _swane_err:
        print("SWANE: slicerrc bootstrap failed:", _swane_err)
{SlicerCheckWorker.END_MARKER}
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
        """Return True if the SWANe patch exists and matches the current stub."""
        content = SlicerCheckWorker.read_slicerrc(slicerrc_path)
        if (
            SlicerCheckWorker.BEGIN_MARKER in content
            and SlicerCheckWorker.END_MARKER in content
        ):
            start = content.index(SlicerCheckWorker.BEGIN_MARKER)
            end = content.index(SlicerCheckWorker.END_MARKER) + len(
                SlicerCheckWorker.END_MARKER
            )
            current_patch = content[start:end]
            return (
                current_patch.strip() == SlicerCheckWorker.build_startup_patch().strip()
            )
        return False

    # -------------------------
    # Add or replace patch
    # -------------------------
    @staticmethod
    def _strip_marked_block(content, begin_marker, end_marker):
        """Return content with a single begin/end-delimited block removed."""
        if begin_marker in content and end_marker in content:
            start = content.index(begin_marker)
            end = content.index(end_marker) + len(end_marker)
            return content[:start] + content[end:]
        return content

    @staticmethod
    def add_slicer_startup_patch():
        """Add the SWANe patch to slicerrc.py. Replaces an outdated patch if different."""
        slicerrc_path = os.path.expanduser("~/.slicerrc.py")

        # Always drop legacy blocks from superseded SWANe versions, even when
        # the current patch is already up to date.
        content = SlicerCheckWorker.read_slicerrc(slicerrc_path)
        cleaned = content
        for begin_marker, end_marker in SlicerCheckWorker.LEGACY_MARKERS:
            cleaned = SlicerCheckWorker._strip_marked_block(
                cleaned, begin_marker, end_marker
            )
        if cleaned != content:
            SlicerCheckWorker.write_slicerrc(slicerrc_path, cleaned)

        if SlicerCheckWorker.check_patch(slicerrc_path):
            return

        # Remove old (mismatched) SWANe patch if present
        content = SlicerCheckWorker.remove_patch(slicerrc_path, return_content=True)

        # Ensure trailing newline
        if content and not content.endswith("\n"):
            content += "\n"

        # Append the new patch
        content += SlicerCheckWorker.build_startup_patch() + "\n"
        SlicerCheckWorker.write_slicerrc(slicerrc_path, content)

    # -------------------------
    # Remove patch
    # -------------------------
    @staticmethod
    def remove_patch(slicerrc_path, return_content=False):
        """Remove the SWANe patch from slicerrc.py, leaving the rest untouched."""
        content = SlicerCheckWorker.read_slicerrc(slicerrc_path)
        if (
            SlicerCheckWorker.BEGIN_MARKER in content
            and SlicerCheckWorker.END_MARKER in content
        ):
            start = content.index(SlicerCheckWorker.BEGIN_MARKER)
            end = content.index(SlicerCheckWorker.END_MARKER) + len(
                SlicerCheckWorker.END_MARKER
            )
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
                        + ",".join(DependencyManager.SLICER_MODULES)
                    )
                    output3 = subprocess.run(
                        cmd3, shell=True, stdout=subprocess.PIPE
                    ).stdout.decode("utf-8")
                    if "MODULE FOUND" in output3:
                        state = DependenceStatus.DETECTED
                        label = strings.check_dep_slicer_found % slicer_version
                        SlicerCheckWorker.add_slicer_startup_patch()
                    else:
                        missing_modules = ", ".join(DependencyManager.SLICER_MODULES)
                        for line in output3.splitlines():
                            if "MODULE MISSING:" in line:
                                missing_modules = line.split("MODULE MISSING:", 1)[
                                    1
                                ].strip()
                                break
                        state = DependenceStatus.WARNING
                        label = strings.check_dep_slicer_error2 % missing_modules

        self.signal.slicer.emit(cmd, slicer_version, label, state)

    def terminate(self):
        return
