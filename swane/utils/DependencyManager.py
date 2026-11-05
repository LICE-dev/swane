# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import functools
import importlib.metadata
import importlib.util
import os
import subprocess
import re
from shutil import which
from swane.resources import strings
from packaging import version
from swane.config.ConfigManager import ConfigManager
from swane.workers.worker_pool import start_worker
from enum import Enum, auto
from swane.utils.ResourceManager import ResourceManager
from swane.utils.platform_and_tools_utils import is_linux
from swane.utils import freesurfer_mcr
from swane.utils.LicenseReference import (
    FSL,
    FREESURFER,
    DCM2NIIX,
    ANTSPYX,
    ANTSPYNET,
    DIPY,
)
from swane.utils.license_consent import version_with_license


class DependenceStatus(Enum):
    DETECTED = auto()
    WARNING = auto()
    MISSING = auto()
    CHECKING = auto()


class Dependence:
    """
    An object with a dependence information
    """

    def __init__(
        self,
        state: DependenceStatus,
        label: str,
        state2: DependenceStatus = DependenceStatus.MISSING,
        detected_version: str = None,
    ):
        """
        Parameters
        ----------
        state: DependenceStatus
            A value describing the dependence status
        label: str
            A string to inform the user about the depence status
        state2: DependenceStatus
            A value describing a subdependence status
        detected_version: str
            Raw version already discovered while checking the dependency.
        """

        self.state: DependenceStatus = state
        self.state2 = DependenceStatus.MISSING
        self.label = None
        self.detected_version = None
        self.update(state, label, state2, detected_version)

    def update(
        self,
        state: DependenceStatus,
        label: str,
        state2: DependenceStatus = DependenceStatus.MISSING,
        detected_version: str = None,
    ):
        """
        Parameters
        ----------
        state: DependenceStatus
            A value in DependenceStatus describing the dependence status
        label: str
            A string to inform the user about the depence status
        state2: DependenceStatus
            A value in DependenceStatus describing a subdependence status
        detected_version: str
            Raw dependency version associated with this state.
        """

        if state in DependenceStatus:
            self.state = state
            self.label = label
            self.state2 = state2
            self.detected_version = detected_version
        else:
            self.state = DependenceStatus.MISSING
            self.state2 = DependenceStatus.MISSING
            self.label = strings.check_dep_generic_error
            self.detected_version = None


@functools.lru_cache(maxsize=1)
def _has_en_us_locale() -> bool:
    """Return True if en_US.utf8 locale is present on Linux, always True on other OS."""
    if not is_linux():
        return True
    try:
        res = subprocess.run(
            ["locale", "-a"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        out = res.stdout.lower()
        return "en_us.utf8" in out or "en_us.utf-8" in out
    except Exception:
        return False


def _read_first_line(path: str) -> str | None:
    """Returns the first line of a text file, None if it is unreadable or empty."""
    try:
        with open(path, encoding="utf-8") as fobj:
            lines = fobj.read().splitlines()
    except OSError:
        return None
    return lines[0] if lines else None


def _read_fsl_version() -> str | None:
    """
    Reads the installed FSL version from $FSLDIR/etc/fslversion, as
    nipype.interfaces.fsl.Info.version() does, without importing Nipype
    (importing nipype.interfaces.fsl takes seconds on GUI startup).

    Returns
    -------
    The version string, None if FSL is not found.
    """
    fsldir = os.environ.get("FSLDIR")
    if not fsldir:
        return None
    return _read_first_line(os.path.join(fsldir, "etc", "fslversion"))


def _freesurfer_looseversion(raw_version: str) -> str:
    """
    Extracts the numeric version from a FreeSurfer build-stamp line.

    Adapted from nipype.interfaces.freesurfer.base.Info.looseversion() (Nipype,
    Apache License 2.0, see NOTICE.md) to avoid importing Nipype on GUI startup.

    Parameters
    ----------
    raw_version: str
        The first line of $FREESURFER_HOME/build-stamp.txt.

    Returns
    -------
    The version string (e.g. "7.4.1").
    """
    vinfo = raw_version.rstrip().split("-")
    try:
        int(vinfo[-1], 16)
    except ValueError:
        githash = ""
    else:
        githash = "." + vinfo[-1]

    # As of FreeSurfer v6.0.0, the final component is a githash
    if githash:
        if vinfo[3] == "dev":
            return "6.0.0-dev" + githash
        if vinfo[5][0] == "v":
            return vinfo[5][1:]
        if vinfo[3].count(".") == 2:
            # e.g. freesurfer-linux-centos7_x86_64-7.1.0-20200511-813297b
            return vinfo[3]
        raise RuntimeError("Unknown version string: " + raw_version)
    # Pre-6.0.0 heuristics
    if "dev" in raw_version:
        return vinfo[-1] + "-dev"
    return raw_version.rstrip().split("-v")[-1]


def _read_freesurfer_version() -> tuple[str | None, str | None]:
    """
    Reads the installed FreeSurfer version from $FREESURFER_HOME/build-stamp.txt,
    as nipype.interfaces.freesurfer.Info does, without importing Nipype.

    Returns
    -------
    A (raw build-stamp, numeric version) tuple, (None, None) if FreeSurfer is
    not found or its version string is not recognized.
    """
    fs_home = os.environ.get("FREESURFER_HOME")
    if not fs_home:
        return None, None
    raw_version = _read_first_line(os.path.join(fs_home, "build-stamp.txt"))
    if raw_version is None:
        return None, None
    try:
        return raw_version, _freesurfer_looseversion(raw_version)
    except (IndexError, RuntimeError):
        return None, None


class DependencyManager:
    """
    Manager for checking dependencies and reporting messages about them
    """

    # 6.0.7.8 ships eddy 2401, the first to accept --nthr (CustomEddy passes it).
    MIN_FSL_VERSION = "6.0.7.8"
    # Kept in sync with the antspyx pin in setup.py.
    MIN_ANTSPYX_VERSION = "0.6.1"
    # Kept in sync with the antspynet pin in setup.py.
    MIN_ANTSPYNET_VERSION = "0.3.2"
    # Kept in sync with the dipy pin in setup.py.
    MIN_DIPY_VERSION = "1.12.1"
    MIN_FREESURFER_VERSION = "7.3.2"
    SYNTH_FREESURFER_VERSION = "8.1.0"
    MIN_SLICER_VERSION = "5.2.1"
    FREESURFER_MATLAB_COMMAND = "checkMCR.sh"
    FREESURFER_MATLAB_REGEXP = r"(fs_install_mcr\s+R[0-9A-Za-z]+)"
    FSL_TCSH_COMMAND = "tcsh"
    FLS_LOCALE_COMMAND = "locale -a | grep en_US.utf8 >/dev/null || false "
    SLICER_MODULES = ["SlicerFreeSurfer", "SurfaceWrapSolidify"]

    def __init__(self):
        self.dcm2niix = DependencyManager.check_dcm2niix()
        self.fsl = DependencyManager.check_fsl()
        self.antspyx = DependencyManager.check_antspyx()
        self.antspynet = DependencyManager.check_antspynet()
        self.dipy = DependencyManager.check_dipy()
        self.freesurfer = DependencyManager.check_freesurfer()
        self.graphviz = DependencyManager.check_graphviz()

    def is_fsl(self=None) -> bool:
        """
        Returns
        -------
        True if fsl is detected (even if outdated).

        """
        if self is not None:
            return self.fsl.state != DependenceStatus.MISSING
        return DependencyManager.check_fsl().state != DependenceStatus.MISSING

    def is_dcm2niix(self) -> bool:
        """
        Returns
        -------
        True if dcm2niix is detected.

        """
        return self.dcm2niix.state == DependenceStatus.DETECTED

    def is_graphviz(self) -> bool:
        """
        Returns
        -------
        True if graphviz is detected.

        """
        return self.graphviz.state == DependenceStatus.DETECTED

    def is_freesurfer(self) -> bool:
        """
        Returns
        -------
        True if freesurfer is detected and configured (even if outdated).

        """
        return self.freesurfer.state != DependenceStatus.MISSING

    def is_freesurfer_matlab(self) -> bool:
        """
        Returns
        -------
        True if freesurfer matlab runtime is detected.

        """
        return self.freesurfer.state2 != DependenceStatus.MISSING

    def is_freesurfer_synth(self=None) -> bool:
        """
        Returns
        -------
        True if freesurfer version contains synth commands.
        """
        detected = (
            getattr(getattr(self, "freesurfer", None), "detected_version", None)
            if self is not None
            else None
        )
        if detected is not None:
            freesurfer_version = detected
        else:
            _, freesurfer_version = _read_freesurfer_version()
            if freesurfer_version is None:
                return False
        try:
            found_version = version.parse(freesurfer_version)
        except Exception:
            return False

        return found_version >= version.parse(
            DependencyManager.SYNTH_FREESURFER_VERSION
        )

    def is_antspyx(self=None) -> bool:
        """
        Returns
        -------
        True if the antspyx package is importable (even if outdated).

        """
        # Instance callers already paid the import/version-check cost in
        # ``__init__``. Keep class-level calls working for prerelease capability
        # probes, but do not repeat the check during normal GUI startup.
        if self is not None:
            return self.antspyx.state != DependenceStatus.MISSING
        return DependencyManager.check_antspyx().state != DependenceStatus.MISSING

    def is_antspynet(self=None) -> bool:
        """
        Returns
        -------
        True if the antspynet package is importable (even if outdated).
        """
        if self is not None:
            return self.antspynet.state != DependenceStatus.MISSING
        return DependencyManager.check_antspynet().state != DependenceStatus.MISSING

    def is_dipy(self=None) -> bool:
        """
        Returns
        -------
        True if the dipy package is importable (even if outdated).
        """
        if self is not None:
            return self.dipy.state != DependenceStatus.MISSING
        return DependencyManager.check_dipy().state != DependenceStatus.MISSING

    @staticmethod
    def is_nilearn() -> bool:
        """
        Returns
        -------
        True if the nilearn package is importable.

        """
        try:
            return importlib.util.find_spec("nilearn") is not None
        except Exception:
            return False

    @staticmethod
    def is_slicer(config: ConfigManager) -> bool:
        """
        Parameters
        ----------
        config: ConfigManager
            The global application preferences

        Returns
        -------
        True if the application preference has a valide Slicer path
        """

        if config is None or not config.global_config:
            return False

        current_slicer_path = config.get_slicer_path()
        if current_slicer_path == "" or not os.path.exists(current_slicer_path):
            return False

        return True

    @staticmethod
    def need_slicer_check(config: ConfigManager) -> bool:
        """
        Parameters
        ----------
        config: ConfigManager
            The global application preferences

        Returns
        -------
        check_slicer: bool
            True if the application needs to check for Slicer dependency
        """

        if config is None or not config.global_config:
            return False

        if not DependencyManager.is_slicer(config):
            return True

        if not DependencyManager.check_slicer_version(config.get_slicer_version()):
            return True

        if config.get_slicer_validator():
            return True

        # Fast filesystem-only revalidation of what the last full check
        # recorded: any drift sends the application back to the full check.
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        if not SlicerCheckWorker.is_slicer_executable(config.get_slicer_path()):
            return True

        if not SlicerCheckWorker.extensions_state_is_valid(
            config.get_slicer_extensions_state(), DependencyManager.SLICER_MODULES
        ):
            return True

        return False

    @staticmethod
    def check_slicer_version(slicer_version: str) -> bool:
        """

        Parameters
        ----------
        slicer_version: str
            The Slicer version to compare with MIN_SLICER_VERSION

        Returns
        -------
        True if the Slicer version is newer or equal to MIN_SLICER_VERSION

        """
        if slicer_version is None or slicer_version == "":
            return False
        try:
            return version.parse(slicer_version) >= version.parse(
                DependencyManager.MIN_SLICER_VERSION
            )
        except:
            return False

    @staticmethod
    def check_slicer(
        current_slicer_path: str,
        callback_func: callable,
        extensions_callback: callable = None,
    ):
        """
        Start a thread to scan the computer for Slicer
        Parameters
        ----------
        current_slicer_path: ConfigManager
            Current Slicer executable path
        callback_func: callable
            The UI function to call after the check thread
        extensions_callback: callable
            Optional, receives the JSON state of the extension install folders
            when every required extension was found
        """
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        if not os.path.exists(current_slicer_path):
            current_slicer_path = ""

        check_slicer_work = SlicerCheckWorker(current_slicer_path)
        check_slicer_work.signal.slicer.connect(callback_func)
        if extensions_callback is not None:
            check_slicer_work.signal.extensions.connect(extensions_callback)
        start_worker(check_slicer_work)

    @staticmethod
    def quick_check_slicer_version(
        slicer_path: str, expected_revision: str, callback_func: callable
    ):
        """
        Start a thread that confirms the Slicer installation still matches the
        revision recorded by the last full check (catches an in-place upgrade).

        Parameters
        ----------
        slicer_path: str
            Slicer executable path
        expected_revision: str
            The Slicer revision recorded by the last full check
        callback_func: callable
            Called with True if the revision matches, False otherwise
        """
        from swane.workers.SlicerCheckWorker import SlicerQuickCheckWorker

        worker = SlicerQuickCheckWorker(slicer_path, expected_revision)
        worker.signal.done.connect(callback_func)
        start_worker(worker)

    @staticmethod
    def check_dcm2niix() -> Dependence:
        """
        Returns
        -------
        A Dependence object with dcm2niix information.
        """
        if importlib.util.find_spec("dcm2niix") is None:
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_dcm2niix_error,
            )
        try:
            dcm2niix_version = importlib.metadata.version("dcm2niix")
            return Dependence(
                DependenceStatus.DETECTED,
                strings.check_dep_dcm2niix_found
                % version_with_license(DCM2NIIX, dcm2niix_version),
            )
        except Exception:
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_dcm2niix_error,
            )

    @staticmethod
    def check_fsl() -> Dependence:
        """
        Returns
        -------
        A Dependence object with fsl information.
        """
        fsl_version = _read_fsl_version()
        if fsl_version is None:
            return Dependence(DependenceStatus.MISSING, strings.check_dep_fsl_error)
        # The first line of etc/fslversion is parsed as is, with no suffix
        # stripped: this matches nipype.interfaces.fsl.Info.version(), whose
        # parse_version returns raw_info.splitlines()[0] (checked on Nipype
        # 1.12.0), so SWANe and the Nipype FSL interfaces see the same version.
        try:
            found_version = version.parse(fsl_version)
        except:
            found_version = version.parse("0")

        # check if locale en_US.utf8 is available
        if not _has_en_us_locale():
            return Dependence(DependenceStatus.MISSING, strings.check_dep_fsl_no_locale)

        fsl_version_lic = version_with_license(FSL, fsl_version)

        # check fsl version
        if found_version < version.parse(DependencyManager.MIN_FSL_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_fsl_wrong_version
                % (fsl_version_lic, DependencyManager.MIN_FSL_VERSION),
                detected_version=fsl_version,
            )

        return Dependence(
            DependenceStatus.DETECTED,
            strings.check_dep_fsl_found % fsl_version_lic,
            detected_version=fsl_version,
        )

    @staticmethod
    def check_antspyx() -> Dependence:
        """
        Returns
        -------
        A Dependence object with antspyx information.
        """
        if importlib.util.find_spec("ants") is None:
            return Dependence(DependenceStatus.MISSING, strings.check_dep_antspyx_error)
        try:
            antspyx_version = importlib.metadata.version("antspyx")
        except Exception:
            return Dependence(DependenceStatus.MISSING, strings.check_dep_antspyx_error)

        try:
            found_version = version.parse(antspyx_version)
        except:
            found_version = version.parse("0")

        antspyx_version_lic = version_with_license(ANTSPYX, antspyx_version)

        if found_version < version.parse(DependencyManager.MIN_ANTSPYX_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_antspyx_wrong_version
                % (antspyx_version_lic, DependencyManager.MIN_ANTSPYX_VERSION),
                detected_version=antspyx_version,
            )

        return Dependence(
            DependenceStatus.DETECTED,
            strings.check_dep_antspyx_found % antspyx_version_lic,
            detected_version=antspyx_version,
        )

    @staticmethod
    def check_antspynet() -> Dependence:
        """
        Returns
        -------
        A Dependence object with antspynet information. Presence is detected
        without importing antspynet (which would load tensorflow) via
        importlib.util.find_spec; the version is read from package metadata.
        """
        if importlib.util.find_spec("antspynet") is None:
            return Dependence(
                DependenceStatus.MISSING, strings.check_dep_antspynet_error
            )
        try:
            antspynet_version = importlib.metadata.version("antspynet")
        except Exception:
            return Dependence(
                DependenceStatus.WARNING, strings.check_dep_antspynet_no_version
            )
        found_version = version.parse(antspynet_version)
        antspynet_version_lic = version_with_license(ANTSPYNET, antspynet_version)
        if found_version < version.parse(DependencyManager.MIN_ANTSPYNET_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_antspynet_wrong_version
                % (antspynet_version_lic, DependencyManager.MIN_ANTSPYNET_VERSION),
            )
        return Dependence(
            DependenceStatus.DETECTED,
            strings.check_dep_antspynet_found % antspynet_version_lic,
        )

    @staticmethod
    def check_dipy() -> Dependence:
        """
        Returns
        -------
        A Dependence object with dipy information. Presence is detected
        without importing dipy via importlib.util.find_spec; the version is
        read from package metadata.
        """
        if importlib.util.find_spec("dipy") is None:
            return Dependence(DependenceStatus.MISSING, strings.check_dep_dipy_error)
        try:
            dipy_version = importlib.metadata.version("dipy")
        except Exception:
            return Dependence(
                DependenceStatus.WARNING, strings.check_dep_dipy_no_version
            )
        found_version = version.parse(dipy_version)
        dipy_version_lic = version_with_license(DIPY, dipy_version)
        if found_version < version.parse(DependencyManager.MIN_DIPY_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_dipy_wrong_version
                % (dipy_version_lic, DependencyManager.MIN_DIPY_VERSION),
            )
        return Dependence(
            DependenceStatus.DETECTED,
            strings.check_dep_dipy_found % dipy_version_lic,
        )

    @staticmethod
    def check_graphviz() -> Dependence:
        """
        Returns
        -------
        A Dependence object with graphviz information.
        """
        if which("dot") is None:
            return Dependence(DependenceStatus.WARNING, strings.check_dep_graph_error)
        return Dependence(DependenceStatus.DETECTED, strings.check_dep_graph_found)

    @staticmethod
    def check_freesurfer() -> Dependence:
        """
        Returns
        -------
        A Dependence object with freesurfer and freesurfer matlab runtime information.
        """

        # FS installed
        raw_version, freesurfer_version = _read_freesurfer_version()
        if raw_version is None or freesurfer_version is None:
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_fs_error1,
                DependenceStatus.MISSING,
            )
        # Version string with an inline license link (used in every label that
        # reports the version); the raw freesurfer_version is kept for parsing.
        fs_ver = version_with_license(FREESURFER, freesurfer_version)

        # FS version file presence
        if "FREESURFER_HOME" not in os.environ:
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_fs_error2 % fs_ver,
                DependenceStatus.MISSING,
            )

        # FreeSurfer license file check
        license_file = os.getenv("FS_LICENSE")
        if not license_file or not os.path.isfile(license_file):
            candidates = [
                os.path.join(os.path.expanduser("~"), "license.txt"),
                os.path.join(os.environ.get("FREESURFER_HOME", ""), "license.txt"),
                os.path.join(os.environ.get("FREESURFER_HOME", ""), ".license"),
            ]
            license_file = next(
                (path for path in candidates if os.path.isfile(path)),
                None,
            )
            if license_file is None:
                return Dependence(
                    DependenceStatus.MISSING,
                    strings.check_dep_fs_error4 % fs_ver,
                    DependenceStatus.MISSING,
                )
            os.environ["FS_LICENSE"] = license_file

        # FreeSurfer minimum version
        try:
            found_version = version.parse(freesurfer_version)
        except:
            found_version = version.parse("0")
        if found_version < version.parse(DependencyManager.MIN_FREESURFER_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_fs_outdated_version
                % (fs_ver, DependencyManager.MIN_FREESURFER_VERSION),
                detected_version=freesurfer_version,
            )

        # tcsh shell installed
        if which(DependencyManager.FSL_TCSH_COMMAND) is None:
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_fs_no_tcsh % fs_ver,
                DependenceStatus.MISSING,
                detected_version=freesurfer_version,
            )

        # FS matlab runtime
        mcr_cmd = which(DependencyManager.FREESURFER_MATLAB_COMMAND)
        if not mcr_cmd and "FREESURFER_HOME" in os.environ:
            candidate = os.path.join(
                os.environ["FREESURFER_HOME"],
                "bin",
                DependencyManager.FREESURFER_MATLAB_COMMAND,
            )
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                mcr_cmd = candidate

        output = ""
        if not mcr_cmd:
            matlab_found = False
        else:
            try:
                res = subprocess.run(
                    [mcr_cmd],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    shell=False,
                )
                matlab_found = res.returncode == 0
                output = (res.stdout or "") + (res.stderr or "")
            except Exception:
                matlab_found = False

        # checkMCR.sh only checks that the runtime folder exists: on Linux,
        # also check that the runtime loads (glibc >= 2.41 can refuse it).
        mcr_load_error = ""
        if matlab_found and is_linux():
            mcr_root = freesurfer_mcr.find_mcr_root(os.environ["FREESURFER_HOME"])
            error = freesurfer_mcr.mcr_load_error(mcr_root) if mcr_root else None
            if error is not None:
                matlab_found = False
                if freesurfer_mcr.EXECSTACK_ERROR in error:
                    mcr_load_error = strings.check_dep_fs_error_matlab_execstack % (
                        freesurfer_mcr.glibc_version() or "glibc"
                    )
                else:
                    mcr_load_error = strings.check_dep_fs_error_matlab_load % error

        fs_dep = DependenceStatus.DETECTED
        matlab_dep = (
            DependenceStatus.DETECTED if matlab_found else DependenceStatus.MISSING
        )

        if found_version < version.parse(DependencyManager.SYNTH_FREESURFER_VERSION):
            error_string = strings.check_dep_fs_synth_version % (
                fs_ver,
                DependencyManager.SYNTH_FREESURFER_VERSION,
            )
            fs_dep = DependenceStatus.WARNING
        elif (
            ResourceManager.total_memory_gb()
            < ResourceManager.synth_reconall_ram_requirements()
        ):
            error_string = strings.check_dep_fs_low_ram % (
                fs_ver,
                ResourceManager.synth_reconall_ram_requirements(),
            )
            fs_dep = DependenceStatus.WARNING
        else:
            error_string = strings.check_dep_fs_found % fs_ver

        if not matlab_found:
            fs_dep = DependenceStatus.WARNING

            match = re.search(DependencyManager.FREESURFER_MATLAB_REGEXP, output)
            if mcr_load_error:
                error_string += mcr_load_error
            elif match:
                install_cmd = match.group(1)
                error_string += strings.check_dep_fs_error_matlab_command % install_cmd
            else:
                error_string += strings.check_dep_fs_error_matlab_no_command

        return Dependence(
            fs_dep,
            error_string,
            matlab_dep,
            detected_version=freesurfer_version,
        )
