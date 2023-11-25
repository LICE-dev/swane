import os
from shutil import which
from nipype.interfaces import dcm2nii, fsl, freesurfer
from swane import strings
from packaging import version


class DependencyManager:

    MIN_FSL_VERSION = "6.0.6"
    MIN_FREESURFER_VERSION = "7.3.2"
    MIN_SLICER_VERSION = "5.8.0"

    def __init__(self):
        self.dcm2niix = DependencyManager.check_dcm2niix()
        self.fsl = DependencyManager.check_fsl()
        self.freesurfer = DependencyManager.check_freesurfer()
        self.graphviz = DependencyManager.check_graphviz()

    def is_fsl(self):
        return self.fsl.state != Dependence.MISSING

    def is_dcm2niix(self):
        return self.dcm2niix.state != Dependence.MISSING

    def is_graphviz(self):
        return self.graphviz.state != Dependence.MISSING

    def is_freesurfer(self):
        return [self.freesurfer.state != Dependence.MISSING, self.freesurfer.state2 != Dependence.MISSING]

    @staticmethod
    def check_slicer_version(slicer_version):
        if slicer_version is None or slicer_version == "":
            return False
        return version.parse(slicer_version) >= version.parse(DependencyManager.MIN_SLICER_VERSION)

    @staticmethod
    def check_dcm2niix():
        dcm2niix_version = dcm2nii.Info.version()
        if dcm2niix_version is None:
            return Dependence(Dependence.MISSING, strings.check_dep_dcm2niix_error)
        return Dependence(Dependence.DETECTED, strings.check_dep_dcm2niix_found % str(dcm2niix_version))

    @staticmethod
    def check_fsl():
        fsl_version = fsl.base.Info.version()
        if fsl_version is None:
            return Dependence(Dependence.MISSING, strings.check_dep_fsl_error)
        if version.parse(fsl_version) < version.parse(DependencyManager.MIN_FSL_VERSION):
            return Dependence(Dependence.WARNING, strings.check_dep_fsl_wrong_version % (fsl_version, DependencyManager.MIN_FSL_VERSION))
        return Dependence(Dependence.DETECTED, strings.check_dep_fsl_found % fsl_version)

    @staticmethod
    def check_graphviz():
        if which("dot") is None:
            return Dependence(Dependence.MISSING, strings.check_dep_graph_error)
        return Dependence(Dependence.DETECTED, strings.check_dep_graph_found)

    @staticmethod
    def check_freesurfer():
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


class Dependence:
    DETECTED = 1
    WARNING = 0
    MISSING = -1
    STATES = [DETECTED, WARNING, MISSING]

    def __init__(self, state, label, state2=MISSING):
        self.state = None
        self.state2 = Dependence.MISSING
        self.label = None
        self.update(state, label, state2)

    def update(self, state, label, state2=MISSING):
        if state in Dependence.STATES:
            self.state = state
            self.label = label
            self.state2 = state2
        else:
            self.state = Dependence.MISSING
            self.state2 = Dependence.MISSING
            self.label = strings.check_dep_generic_error
