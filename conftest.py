"""Repository-root pytest bootstrap, loaded before the ``swane`` package.

``swane/tests`` is a package, so pytest imports ``swane`` (whose ``__init__``
imports ``swane.patches`` and through it ``nipype.interfaces.fsl``) *before*
``swane/tests/conftest.py`` can run. Anything that has to precede that first
nipype import therefore lives here, in a module that imports neither swane nor
nipype at load time: the Windows ``pwd`` stub and the nipype version fallback.
"""

import importlib.util
import os

# On Windows, nipype.pipeline.plugins only imports once SWANe's pwd stub is in
# place. windows_compat is loaded from its file path, not as
# ``swane.patches.windows_compat``, so that ``swane`` is not imported yet.
_windows_compat_spec = importlib.util.spec_from_file_location(
    "_swane_windows_compat_bootstrap",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "swane",
        "patches",
        "windows_compat.py",
    ),
)
_windows_compat = importlib.util.module_from_spec(_windows_compat_spec)
_windows_compat_spec.loader.exec_module(_windows_compat)
_windows_compat.install_pwd_stub()

# Some nipype FSL interfaces pick their *input spec class* once, at import
# time, based on nipype.interfaces.fsl.base.Info.version() (e.g. FILMGLS:
# FSL <=5.0.6 lacks the tcon_file/fcon_file inputs swane wires — see
# fMRI_task_workflow). On a box without a real FSL install (e.g. the
# Windows dev machine these tests must also run on) that version is None
# and nipype silently falls back to the old/reduced interface, breaking
# workflow construction for reasons that have nothing to do with swane's
# code. Patch nipype's common PackageInfo.version() so *only* FSL interface
# classes (nipype.interfaces.fsl.*), and only when the real detection comes
# up empty, report a modern FSL version (>= 6.0, matching the
# FSLOUTPUTTYPE default in swane/tests/conftest.py) instead of None. Where a real FSL install is present (e.g. the
# heavy/integration tests), real detection wins and this fallback never
# triggers. Must run before anything below imports nipype.interfaces.fsl
# (importing swane does, via swane.patches).
#
# The same reasoning applies to FreeSurfer, for a different trait: nipype's
# FSCommand fills ``subjects_dir`` from SUBJECTS_DIR *only when FreeSurfer is
# detected* (freesurfer.base.Info.subjectsdir), so the assembled graph — and
# therefore the golden snapshots — would otherwise depend on whether the tool
# happens to be installed. Faking the version here makes construction identical
# on both, and the snapshot renderer rewrites the directory to a token.
_FALLBACK_VERSIONS = {
    "nipype.interfaces.fsl": "6.0.7.22",
    "nipype.interfaces.freesurfer": "8.0.0",
}
from nipype.interfaces.base import core as _nipype_core

_real_package_version = _nipype_core.PackageInfo.version.__func__


def _package_version_with_fallback(klass):
    version = _real_package_version(klass)
    if version is None:
        for prefix, fallback in _FALLBACK_VERSIONS.items():
            if klass.__module__.startswith(prefix):
                return fallback
    return version


_nipype_core.PackageInfo.version = classmethod(_package_version_with_fallback)
