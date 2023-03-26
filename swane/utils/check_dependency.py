import os
from shutil import which
from nipype.interfaces import dcm2nii, fsl, freesurfer
from swane import strings


def is_tool(name):
    """Check whether `name` is on PATH and marked as executable."""
    return which(name) is not None


def check_dcm2niix():
    version = dcm2nii.Info.version()
    if version is None:
        return strings.check_dep_dcm2niix_error, False
    return (strings.check_dep_dcm2niix_found % str(version)), True


def check_fsl():
    version = fsl.base.Info.version()
    if version is None:
        return strings.check_dep_fsl_error, False
    return (strings.check_dep_fsl_found % str(version)), True


def check_freesurfer():
    if freesurfer.base.Info.version() is None:
        return strings.check_dep_fs_error1, [False, False]

    version = freesurfer.base.Info.looseversion()
    if "FREESURFER_HOME" not in os.environ:
        return (strings.check_dep_fs_error2 % str(version)), [False, False]
    file = os.path.join(os.environ["FREESURFER_HOME"], "license.txt")
    if os.path.exists(file):
        mrc = os.system("checkMCR.sh")
        if mrc == 0:
            return (strings.check_dep_fs_found % str(version)), [True, True]
        # TODO: facciamo un parse dell'output del comando per dare all'utente il comando di installazione? o forse è meglio non basarsi sul formato attuale dell'output e linkare direttamente la pagina ufficiale?
        return (strings.check_dep_fs_error3 % str(version)), [True, False]

    return (strings.check_dep_fs_error4 % str(version)), [False, False]


def check_graphviz():
    if which("dot") is None:
        return strings.check_dep_graph_error, False
    return strings.check_dep_graph_found, True





