import os
from shutil import which
from nipype.interfaces import dcm2nii, fsl, freesurfer
from swane import strings
from packaging import version


class Dependence:
    """
    An object with a dependence information
    """
    DETECTED = 1
    WARNING = 0
    MISSING = -1
    STATES = [DETECTED, WARNING, MISSING]

    def __init__(self, state: int, label: str, state2: int = MISSING):
        """
        Parameters
        ----------
        state: int
            A value in Dependence.STATES describing the dependence status
        label: str
            A string to inform the user about the depence status
        state2: int
            A value in Dependence.STATES describing a subdependence status
        """

        self.state = None
        self.state2 = Dependence.MISSING
        self.label = None
        self.update(state, label, state2)

    def update(self, state: int, label: str, state2: int = MISSING):
        """
        Parameters
        ----------
        state: int
            A value in Dependence.STATES describing the dependence status
        label: str
            A string to inform the user about the depence status
        state2: int
            A value in Dependence.STATES describing a subdependence status
        """
        
        if state in Dependence.STATES:
            self.state = state
            self.label = label
            self.state2 = state2
        else:
            self.state = Dependence.MISSING
            self.state2 = Dependence.MISSING
            self.label = strings.check_dep_generic_error


class DependencyManager:
    """
    Manager for checking dependencies and reporting messages about them
    """

    MIN_FSL_VERSION = "6.0.6"
    MIN_FREESURFER_VERSION = "7.3.2"
    MIN_SLICER_VERSION = "5.2.0"

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
        return self.fsl.state != Dependence.MISSING

    def is_dcm2niix(self) -> bool:
        """
        Returns
        -------
        True if dcm2niix is detected.

        """
        return self.dcm2niix.state == Dependence.DETECTED

    def is_graphviz(self) -> bool:
        """
        Returns
        -------
        True if graphviz is detected.

        """
        return self.graphviz.state == Dependence.DETECTED

    def is_freesurfer(self) -> [bool, bool]:
        """
        Returns
        -------
        The first bool is True if freesurfer is detected and configured (even if outdated).
        The second bool is True if freesurfer matlab runtime is detected.

        """
        return [self.freesurfer.state != Dependence.MISSING, self.freesurfer.state2 != Dependence.MISSING]

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
        return version.parse(slicer_version) >= version.parse(DependencyManager.MIN_SLICER_VERSION)

    @staticmethod
    def check_dcm2niix() -> Dependence:
        """
        Returns
        -------
        A Dependence object with dcm2niix informations.
        """
        dcm2niix_version = dcm2nii.Info.version()
        if dcm2niix_version is None:
            return Dependence(Dependence.MISSING, strings.check_dep_dcm2niix_error)
        return Dependence(Dependence.DETECTED, strings.check_dep_dcm2niix_found % str(dcm2niix_version))

    @staticmethod
    def check_fsl() -> Dependence:
        """
        Returns
        -------
        A Dependence object with fsl informations.
        """
        fsl_version = fsl.base.Info.version()
        if fsl_version is None:
            return Dependence(Dependence.MISSING, strings.check_dep_fsl_error)
        if version.parse(fsl_version) < version.parse(DependencyManager.MIN_FSL_VERSION):
            return Dependence(Dependence.WARNING, strings.check_dep_fsl_wrong_version % (fsl_version, DependencyManager.MIN_FSL_VERSION))
        return Dependence(Dependence.DETECTED, strings.check_dep_fsl_found % fsl_version)

    @staticmethod
    def check_graphviz() -> Dependence:
        """
        Returns
        -------
        A Dependence object with graphviz informations.
        """
        if which("dot") is None:
            return Dependence(Dependence.WARNING, strings.check_dep_graph_error)
        return Dependence(Dependence.DETECTED, strings.check_dep_graph_found)

    @staticmethod
    def check_freesurfer() -> Dependence:
        """
        Returns
        -------
        A Dependence object with freesurfer and freesurfer matlab runtime informations.
        """
        if freesurfer.base.Info.version() is None:
            return Dependence(Dependence.MISSING, strings.check_dep_fs_error1, Dependence.MISSING)
        freesurfer_version = str(freesurfer.base.Info.looseversion())
        if "FREESURFER_HOME" not in os.environ:
            return Dependence(Dependence.MISSING, strings.check_dep_fs_error2 % freesurfer_version, Dependence.MISSING)
        file = os.path.join(os.environ["FREESURFER_HOME"], "license.txt")
        if not os.path.exists(file):
            return Dependence(Dependence.MISSING, strings.check_dep_fs_error4 % freesurfer_version, Dependence.MISSING)
        if version.parse(freesurfer_version) < version.parse(DependencyManager.MIN_FREESURFER_VERSION):
            return Dependence(Dependence.WARNING, strings.check_dep_fs_wrong_version % (freesurfer_version, DependencyManager.MIN_FSL_VERSION))
        mrc = os.system("checkMCR.sh")
        if mrc != 0:
            # TODO: facciamo un parse dell'output del comando per dare all'utente il comando di installazione? o forse è meglio non basarsi sul formato attuale dell'output e linkare direttamente la pagina ufficiale?
            return Dependence(Dependence.WARNING, strings.check_dep_fs_error3 % freesurfer_version, Dependence.MISSING)
        return Dependence(Dependence.DETECTED, strings.check_dep_fs_found % freesurfer_version, Dependence.DETECTED)


