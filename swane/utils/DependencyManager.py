import os
import subprocess
import re
from shutil import which
from nipype.interfaces import dcm2nii, fsl, freesurfer
from swane import strings
from packaging import version
from swane.config.ConfigManager import ConfigManager
from PySide6.QtCore import QThreadPool
from enum import Enum, auto
from swane.utils.ResourceManager import ResourceManager
from swane.utils.platform_and_tools_utils import is_linux


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
        """

        self.state: DependenceStatus = state
        self.state2 = DependenceStatus.MISSING
        self.label = None
        self.update(state, label, state2)

    def update(
        self,
        state: DependenceStatus,
        label: str,
        state2: DependenceStatus = DependenceStatus.MISSING,
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
        """

        if state in DependenceStatus:
            self.state = state
            self.label = label
            self.state2 = state2
        else:
            self.state = DependenceStatus.MISSING
            self.state2 = DependenceStatus.MISSING
            self.label = strings.check_dep_generic_error


class DependencyManager:
    """
    Manager for checking dependencies and reporting messages about them
    """

    MIN_FSL_VERSION = "6.0.6"
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
        self.freesurfer = DependencyManager.check_freesurfer()
        self.graphviz = DependencyManager.check_graphviz()

    def is_fsl(self) -> bool:
        """
        Returns
        -------
        True if fsl is detected (even if outdated).

        """
        return self.fsl.state != DependenceStatus.MISSING

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

    @staticmethod
    def is_freesurfer_synth() -> bool:
        """
        Returns
        -------
        True if freesurfer version contains synth commands.

        """
        freesurfer_version = str(freesurfer.base.Info.looseversion())
        try:
            found_version = version.parse(freesurfer_version)
        except:
            return False

        return found_version >= version.parse(
            DependencyManager.SYNTH_FREESURFER_VERSION
        )

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

        check_slicer = False
        if not DependencyManager.is_slicer(config):
            check_slicer = True

        if not DependencyManager.check_slicer_version(config.get_slicer_version()):
            check_slicer = True

        if config.get_slicer_validator():
            check_slicer = True

        return check_slicer

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
    def check_slicer(current_slicer_path: str, callback_func: callable):
        """
        Start a thread to scan the computer for Slicer
        Parameters
        ----------
        current_slicer_path: ConfigManager
            Current Slicer executable path
        callback_func: callable
            The UI function to call after the check thread
        """
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        if not os.path.exists(current_slicer_path):
            current_slicer_path = ""

        check_slicer_work = SlicerCheckWorker(current_slicer_path)
        check_slicer_work.signal.slicer.connect(callback_func)
        QThreadPool.globalInstance().start(check_slicer_work)

    @staticmethod
    def check_dcm2niix() -> Dependence:
        """
        Returns
        -------
        A Dependence object with dcm2niix information.
        """
        dcm2niix_version = dcm2nii.Info.version()
        if dcm2niix_version is None:
            return Dependence(
                DependenceStatus.MISSING, strings.check_dep_dcm2niix_error
            )
        return Dependence(
            DependenceStatus.DETECTED,
            strings.check_dep_dcm2niix_found % str(dcm2niix_version),
        )

    @staticmethod
    def check_fsl() -> Dependence:
        """
        Returns
        -------
        A Dependence object with fsl information.
        """
        fsl_version = fsl.base.Info.version()
        if fsl_version is None:
            return Dependence(DependenceStatus.MISSING, strings.check_dep_fsl_error)
        try:
            found_version = version.parse(fsl_version)
        except:
            found_version = version.parse("0")

        # check if locale en_US.utf8 is available
        if is_linux():
            locale_en = os.system(DependencyManager.FLS_LOCALE_COMMAND)
            if locale_en != 0:
                return Dependence(
                    DependenceStatus.MISSING, strings.check_dep_fsl_no_locale
                )

        # check fsl version
        if found_version < version.parse(DependencyManager.MIN_FSL_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_fsl_wrong_version
                % (fsl_version, DependencyManager.MIN_FSL_VERSION),
            )

        return Dependence(
            DependenceStatus.DETECTED, strings.check_dep_fsl_found % fsl_version
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
        if freesurfer.base.Info.version() is None:
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_fs_error1,
                DependenceStatus.MISSING,
            )
        freesurfer_version = str(freesurfer.base.Info.looseversion())

        # FS version file presence
        if "FREESURFER_HOME" not in os.environ:
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_fs_error2 % freesurfer_version,
                DependenceStatus.MISSING,
            )
        license_file = os.getenv("FS_LICENSE")
        if license_file is None or not os.path.exists(license_file):
            license_file = os.path.join(os.environ["FREESURFER_HOME"], "license.txt")
        if not os.path.exists(license_file):
            return Dependence(
                DependenceStatus.MISSING,
                strings.check_dep_fs_error4 % freesurfer_version,
                DependenceStatus.MISSING,
            )
        try:
            found_version = version.parse(freesurfer_version)
        except:
            found_version = version.parse("0")

        # FS minimum version
        if found_version < version.parse(DependencyManager.MIN_FREESURFER_VERSION):
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_fs_outdated_version
                % (freesurfer_version, DependencyManager.MIN_FREESURFER_VERSION),
            )

        # tcsh shell installed
        if which(DependencyManager.FSL_TCSH_COMMAND) is None:
            return Dependence(
                DependenceStatus.WARNING,
                strings.check_dep_fs_no_tcsh % freesurfer_version,
                DependenceStatus.MISSING,
            )

        # FS matlab runtime
        result = subprocess.run(
            DependencyManager.FREESURFER_MATLAB_COMMAND,
            shell=True,
            capture_output=True,
            text=True,
        )
        matlab_found = result.returncode == 0
        fs_dep = DependenceStatus.DETECTED
        matlab_dep = (
            DependenceStatus.DETECTED if matlab_found else DependenceStatus.MISSING
        )

        if found_version < version.parse(DependencyManager.SYNTH_FREESURFER_VERSION):
            error_string = strings.check_dep_fs_synth_version % (
                freesurfer_version,
                DependencyManager.SYNTH_FREESURFER_VERSION,
            )
            fs_dep = DependenceStatus.WARNING
        elif (
            ResourceManager.total_memory_gb()
            < ResourceManager.synth_reconall_ram_requirements()
        ):
            error_string = strings.check_dep_fs_low_ram % (
                freesurfer_version,
                ResourceManager.synth_reconall_ram_requirements(),
            )
            fs_dep = DependenceStatus.WARNING
        else:
            error_string = strings.check_dep_fs_found % freesurfer_version

        if not matlab_found:
            fs_dep = DependenceStatus.WARNING

            output = result.stdout + result.stderr
            match = re.search(DependencyManager.FREESURFER_MATLAB_REGEXP, output)
            if match:
                install_cmd = match.group(1)
                error_string += strings.check_dep_fs_error_matlab_command % install_cmd
            else:
                error_string += strings.check_dep_fs_error_matlab_no_command

        return Dependence(
            fs_dep,
            error_string,
            matlab_dep,
        )
