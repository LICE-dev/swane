import glob
import json
import locale
import logging
import os
import re
import subprocess

import psutil
from swane.utils.qt_compat import QRunnable, Signal, QObject
from swane.resources import strings
from swane.utils.DependencyManager import DependencyManager, DependenceStatus
from swane.utils.license_consent import version_with_license
from swane.utils.LicenseReference import SLICER
import platform


class SlicerCheckSignaler(QObject):
    slicer = Signal(str, str, str, DependenceStatus)
    # JSON state of the extension install folders, emitted before ``slicer``
    # when every required extension was found
    extensions = Signal(str)


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
    # seconds before a Slicer subprocess is considered hung and killed
    VERSION_TIMEOUT = 60
    MODULE_INSTALL_TIMEOUT = 600

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
    def find_slicer_python(current_slicer_path: str) -> tuple[list[str], str]:
        # If current_slicer_path doeas not exists, replace with a blank string
        # If it is a file, search in its directory
        if not os.path.exists(current_slicer_path):
            current_slicer_path = ""
        resolved_path = (
            os.path.realpath(current_slicer_path) if current_slicer_path else ""
        )
        if os.path.isfile(current_slicer_path):
            current_slicer_path = os.path.dirname(current_slicer_path)
            resolved_path = os.path.dirname(resolved_path)

        if platform.system() == "Windows":
            return (
                SlicerCheckWorker._find_slicer_python_windows(current_slicer_path),
                "../Slicer.exe",
            )

        is_macos = platform.system() == "Darwin"
        if is_macos:
            pattern = "*app/Contents/bin/PythonSlicer"
            rel_path = "../MacOS/Slicer"
            exec_flag = (
                ""  # on macOS -executable is not needed, the .app bundle is sufficient
            )
        else:
            pattern = "*bin/PythonSlicer"
            rel_path = "../Slicer"
            exec_flag = "-executable "

        def run_find(src_path: str, xdev: bool, timeout: int) -> list[str]:
            xdev_flag = "-xdev " if xdev else ""
            cmd = (
                f'find "{src_path}" {xdev_flag}{exec_flag}-type f '
                f'-wholename "{pattern}" -print -quit 2>/dev/null'
            )
            try:
                output = SlicerCheckWorker._decode(
                    subprocess.run(
                        cmd, shell=True, stdout=subprocess.PIPE, timeout=timeout
                    ).stdout
                )
            except subprocess.TimeoutExpired:
                output = ""
            split = output.split("\n")
            while "" in split:
                split.remove("")
            return split

        # If the user specified a path, only search there: the given folder
        # first, then its symlink-resolved twin (e.g. a Slicer launcher
        # linked into a bin folder) and, on macOS, the enclosing .app bundle
        # (the recorded executable is Slicer.app/Contents/MacOS/Slicer, while
        # PythonSlicer sits in the sibling Contents/bin).
        if current_slicer_path != "":
            roots = [current_slicer_path, resolved_path]
            if is_macos:
                roots.append(SlicerCheckWorker._macos_bundle_root(resolved_path))
            result = []
            for root in dict.fromkeys(roots):
                result = run_find(root, xdev=False, timeout=15)
                if result:
                    break
            return result, rel_path

        # Staged search when there is no initial path:
        # 1) $HOME (fast, covers most common user installations)
        # 2) main filesystem with -xdev (avoids external/network mounts)
        # 3) entire filesystem without limits, as a last resort
        home = os.path.expanduser("~")
        stages = [
            (home, False, 10),
            ("/Applications" if is_macos else "/", True, 15),
            ("/", False, 30),
        ]

        for src_path, xdev, timeout in stages:
            result = run_find(src_path, xdev, timeout)
            if result:
                return result, rel_path

        return [], rel_path

    @staticmethod
    def _macos_bundle_root(path: str) -> str:
        """The innermost ``*.app`` folder containing ``path``, else ``path``."""
        candidate = os.path.abspath(path)
        while True:
            if candidate.endswith(".app"):
                return candidate
            parent = os.path.dirname(candidate)
            if parent == candidate:
                return path
            candidate = parent

    @staticmethod
    def _find_slicer_python_windows(current_slicer_path: str) -> list[str]:
        """Locate PythonSlicer.exe without GNU find.

        Slicer's Windows installer puts each version in its own folder, by
        default ``%LOCALAPPDATA%\\slicer.org\\Slicer <version>`` (per user) or
        ``%ProgramFiles%\\Slicer <version>`` (all users). Newest version first:
        see :meth:`_windows_install_rank`.
        """
        if current_slicer_path:
            roots = [current_slicer_path]
        else:
            roots = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "slicer.org"),
                os.environ.get("ProgramW6432", ""),
                os.environ.get("ProgramFiles", ""),
            ]
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            found = []
            for depth in ("", "*", os.path.join("*", "*")):
                pattern = os.path.join(root, depth, "bin", "PythonSlicer.exe")
                found.extend(glob.glob(pattern))
            if found:
                return sorted(
                    set(found),
                    key=SlicerCheckWorker._windows_install_rank,
                    reverse=True,
                )
        return []

    @staticmethod
    def _windows_install_rank(python_slicer: str) -> tuple:
        """Sort key of a found PythonSlicer, higher is newer.

        The build revision in ``bin/SlicerLauncherSettings.ini`` decides, as the
        install folder may have any name; installs without a readable revision
        rank below, by folder name with its numbers compared as numbers
        (``Slicer 5.10.0`` after ``Slicer 5.8.1``).
        """
        revision = SlicerCheckWorker.read_slicer_revision(python_slicer)
        try:
            revision = int(revision)
        except (TypeError, ValueError):
            revision = -1
        name = tuple(
            (1, int(part), "") if part.isdigit() else (0, 0, part)
            for part in re.split(r"(\d+)", python_slicer)
        )
        return revision, name

    @staticmethod
    def parse_extension_report(output: str) -> dict:
        """
        Parse the ``SLICER REVISION:`` / ``MODULE PATH:`` lines printed by
        ``slicer_script_module_install.py``.

        Returns
        -------
        dict
            ``{"revision": str, "paths": {extension name: install folder}}``
        """
        state = {"revision": "", "paths": {}}
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("SLICER REVISION:"):
                state["revision"] = line.split(":", 1)[1].strip()
            elif line.startswith("MODULE PATH:"):
                name, sep, path = line.split(":", 1)[1].partition("=")
                if sep and name.strip() and path.strip():
                    state["paths"][name.strip()] = path.strip()
        return state

    @staticmethod
    def extensions_state_is_valid(raw_state: str, modules: list) -> bool:
        """
        Cheap, filesystem-only check of the state recorded by a full check.

        Returns
        -------
        bool
            True if the state lists every module and each install folder still
            exists. An empty, malformed or incomplete state is not valid, so the
            caller falls back to the full check.
        """
        try:
            paths = json.loads(raw_state)["paths"]
        except (TypeError, ValueError, KeyError):
            return False
        if not isinstance(paths, dict):
            return False
        return all(
            isinstance(paths.get(module), str) and os.path.isdir(paths[module])
            for module in modules
        )

    @staticmethod
    def is_slicer_executable(slicer_path: str) -> bool:
        """True if the path is a launchable Slicer file (not a folder or a stub)."""
        if not os.path.isfile(slicer_path):
            return False
        return platform.system() == "Windows" or os.access(slicer_path, os.X_OK)

    @staticmethod
    def read_slicer_revision(slicer_path: str) -> str | None:
        """
        Read the Slicer build revision from Slicer's metadata files without
        spawning a subprocess.

        On macOS, checks ``Contents/Info.plist`` (``CFBundleVersion``) and
        ``Contents/bin/SlicerLauncherSettings.ini``.
        On Linux and Windows, checks ``bin/SlicerLauncherSettings.ini``.

        Returns
        -------
        str | None
            The Slicer revision string (e.g. "34045"), or None if unreadable.
        """
        if not slicer_path:
            return None

        resolved = os.path.realpath(slicer_path)
        dirs_to_check = [os.path.dirname(slicer_path), os.path.dirname(resolved)]

        if platform.system() == "Darwin":
            bundle = SlicerCheckWorker._macos_bundle_root(resolved)
            dirs_to_check.extend(
                [
                    os.path.join(bundle, "Contents", "bin"),
                    os.path.join(bundle, "Contents"),
                ]
            )

        candidates = []
        for d in dict.fromkeys(dirs_to_check):
            candidates.extend(
                [
                    os.path.join(d, "bin", "SlicerLauncherSettings.ini"),
                    os.path.join(d, "SlicerLauncherSettings.ini"),
                    os.path.join(d, "..", "bin", "SlicerLauncherSettings.ini"),
                ]
            )

        for candidate in dict.fromkeys(candidates):
            if os.path.isfile(candidate):
                try:
                    import configparser

                    cfg = configparser.ConfigParser(interpolation=None)
                    cfg.read(candidate, encoding="utf-8-sig")
                    if "Application" in cfg and "revision" in cfg["Application"]:
                        rev = cfg["Application"]["revision"].strip()
                        if rev:
                            return rev
                except Exception:
                    continue

        if platform.system() == "Darwin":
            bundle = SlicerCheckWorker._macos_bundle_root(resolved)
            plist_path = os.path.join(bundle, "Contents", "Info.plist")
            if os.path.isfile(plist_path):
                try:
                    import plistlib

                    with open(plist_path, "rb") as fp:
                        plist = plistlib.load(fp)
                        rev = plist.get("CFBundleVersion") or plist.get(
                            "CFBundleShortVersionString"
                        )
                        if rev:
                            return str(rev).strip()
                except Exception:
                    pass

        return None

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
        """Return True if the file holds exactly one SWANe patch and it matches
        the current stub."""
        content = SlicerCheckWorker.read_slicerrc(slicerrc_path)
        blocks = SlicerCheckWorker._find_blocks(
            content, SlicerCheckWorker.BEGIN_MARKER, SlicerCheckWorker.END_MARKER
        )
        if len(blocks) != 1:
            return False
        start, end = blocks[0]
        return (
            content[start:end].strip()
            == SlicerCheckWorker.build_startup_patch().strip()
        )

    # -------------------------
    # Add or replace patch
    # -------------------------
    @staticmethod
    def _find_blocks(content, begin_marker, end_marker):
        """Return the (start, end) span of every complete begin/end block.

        Each end marker is searched after its own begin marker, so a stray end
        marker before a begin (e.g. the user deleted a begin line) is never
        paired with it.
        """
        blocks = []
        pos = 0
        while True:
            start = content.find(begin_marker, pos)
            if start == -1:
                return blocks
            end = content.find(end_marker, start + len(begin_marker))
            if end == -1:
                return blocks
            pos = end + len(end_marker)
            blocks.append((start, pos))

    @staticmethod
    def _strip_marked_block(content, begin_marker, end_marker):
        """Return content with every complete begin/end-delimited block
        removed; text outside those blocks is left untouched."""
        for start, end in reversed(
            SlicerCheckWorker._find_blocks(content, begin_marker, end_marker)
        ):
            content = content[:start] + content[end:]
        return content

    @staticmethod
    def add_slicer_startup_patch() -> bool:
        """
        Add the SWANe patch to slicerrc.py. Replaces an outdated patch if different.

        The file is written only when its content changes. The patch is a
        convenience for SWANe's Slicer helpers, so an unreadable or read-only
        slicerrc never raises: the patch is just left out.

        Returns
        -------
        bool
            False if slicerrc.py could not be read or written.
        """
        try:
            SlicerCheckWorker._add_slicer_startup_patch()
        except (OSError, UnicodeError):
            return False
        return True

    @staticmethod
    def _add_slicer_startup_patch():
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
        new_content = SlicerCheckWorker._strip_marked_block(
            content, SlicerCheckWorker.BEGIN_MARKER, SlicerCheckWorker.END_MARKER
        )
        if return_content:
            return new_content
        if new_content != content:
            SlicerCheckWorker.write_slicerrc(slicerrc_path, new_content)

    @staticmethod
    def _decode(raw: bytes) -> str:
        """Decode a subprocess output: UTF-8, else the locale encoding.

        On Windows Slicer's Python writes piped output in the ANSI code page,
        so a non-ASCII path (e.g. under the user profile) is not valid UTF-8.
        """
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode(locale.getpreferredencoding(False), errors="replace")

    @staticmethod
    def _communicate(cmd: list[str], timeout: float) -> bytes:
        """Run ``cmd`` without a shell and return its stdout.

        On a timeout the whole process tree is killed before
        ``subprocess.TimeoutExpired`` is raised: the Slicer launcher starts the
        real application as a child that inherits the stdout pipe, and reading
        that pipe would otherwise wait for an EOF that never comes.
        """
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        try:
            return proc.communicate(timeout=timeout)[0]
        except subprocess.TimeoutExpired:
            SlicerCheckWorker._kill_tree(proc.pid)
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            raise

    @staticmethod
    def _kill_tree(pid: int):
        """Kill a process and all its descendants."""
        try:
            parent = psutil.Process(pid)
            procs = parent.children(recursive=True) + [parent]
        except psutil.NoSuchProcess:
            return
        for proc in procs:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(procs, timeout=10)

    def _run_slicer(self, cmd: list[str], timeout: float) -> str | None:
        """Slicer's decoded stdout, or None if it cannot run or hangs."""
        try:
            return SlicerCheckWorker._decode(
                SlicerCheckWorker._communicate(cmd, timeout)
            )
        except subprocess.TimeoutExpired:
            logging.getLogger(__name__).warning(
                "3D Slicer did not answer within %s s: %s", timeout, cmd
            )
            return None
        except OSError:
            # stale path / not executable
            return None

    def run(self):
        result = ("", "", strings.check_dep_slicer_error1, DependenceStatus.MISSING)
        try:
            result = self._check()
        except Exception:
            # never leave the caller waiting for a result
            logging.getLogger(__name__).exception("3D Slicer check failed")
        self.signal.slicer.emit(*result)

    def _check(self) -> tuple[str, str, str, DependenceStatus]:
        repeat = True
        cmd = ""
        state: DependenceStatus = DependenceStatus.MISSING
        label = ""
        slicer_version = ""

        while repeat:
            # reset cmd every iteration: otherwise an empty search result would
            # leave a stale path from the previous loop and emit it as valid.
            cmd = ""
            split, rel_path = SlicerCheckWorker.find_slicer_python(
                self.current_slicer_path
            )
            # find slicerpython executable and go back to slicer executable with rel_path
            for entry in split:
                cmd = os.path.abspath(os.path.join(os.path.dirname(entry), rel_path))
                break
            output2 = None
            if cmd != "" and os.path.exists(cmd):
                output2 = self._run_slicer(
                    [cmd, "--version"], SlicerCheckWorker.VERSION_TIMEOUT
                )
                if output2 is None:
                    # stale path / not executable / hung: treat as not found
                    cmd = ""
            if output2 is None:
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
                slicer_version = output2.replace("Slicer ", "").strip()
                if not DependencyManager.check_slicer_version(slicer_version):
                    label = strings.check_dep_slicer_wrong_version % (
                        version_with_license(SLICER, slicer_version),
                        DependencyManager.MIN_SLICER_VERSION,
                    )
                    state = DependenceStatus.WARNING
                else:
                    # Try to automatically install Slicer extensions.
                    # Run without a shell: the script path is a separate argv
                    # element, so an install dir containing spaces survives.
                    module_install_script = os.path.join(
                        os.path.dirname(__file__),
                        "slicer_script_module_install.py",
                    )
                    cmd3 = [
                        cmd,
                        "--no-splash",
                        "--no-main-window",
                        "--python-script",
                        module_install_script,
                        ",".join(DependencyManager.SLICER_MODULES),
                    ]
                    output3 = (
                        self._run_slicer(cmd3, SlicerCheckWorker.MODULE_INSTALL_TIMEOUT)
                        or ""
                    )
                    if "MODULE FOUND" in output3:
                        self.signal.extensions.emit(
                            json.dumps(
                                SlicerCheckWorker.parse_extension_report(output3)
                            )
                        )
                        state = DependenceStatus.DETECTED
                        label = strings.check_dep_slicer_found % version_with_license(
                            SLICER, slicer_version
                        )
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

        return cmd, slicer_version, label, state

    def terminate(self):
        return


class SlicerQuickCheckSignaler(QObject):
    done = Signal(bool)


class SlicerQuickCheckWorker(QRunnable):
    """
    Spawn a thread that confirms the known Slicer installation still matches
    the revision recorded by the last full check (catches an in-place upgrade).
    """

    def __init__(self, slicer_path: str, expected_revision: str):
        super(SlicerQuickCheckWorker, self).__init__()
        self.signal = SlicerQuickCheckSignaler()
        self.slicer_path = slicer_path
        self.expected_revision = expected_revision

    def run(self):
        current_rev = SlicerCheckWorker.read_slicer_revision(self.slicer_path)
        ok = bool(
            current_rev
            and self.expected_revision
            and current_rev == str(self.expected_revision).strip()
        )
        self.signal.done.emit(ok)

    def terminate(self):
        return
