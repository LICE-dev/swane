"""Static registry describing how to locate/display each external tool's license.

This module only points at license *text* for display. It never references any
external tool's source code, and never points FreeSurfer at the per-user
registration key file (that is a personal secret, not the legal license).
"""

import os
from dataclasses import dataclass
from typing import Callable

FSL = "fsl"
FREESURFER = "freesurfer"
SLICER = "slicer"
DCM2NIIX = "dcm2niix"
TOOL_IDS = (FSL, FREESURFER, SLICER, DCM2NIIX)

_BUNDLED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "licenses")


@dataclass(frozen=True)
class LicenseInfo:
    tool_id: str
    display_name: str
    official_url: str
    is_html_online: bool
    installed_path_candidates: Callable[[dict], list]
    bundled_filename: str


def bundled_license_path(info: "LicenseInfo") -> str:
    return os.path.normpath(os.path.join(_BUNDLED_DIR, info.bundled_filename))


def _fsl_candidates(context: dict) -> list:
    fsldir = os.environ.get("FSLDIR", "")
    if not fsldir:
        return []
    return [
        os.path.join(fsldir, "LICENSE"),
        os.path.join(fsldir, "LICENCE"),
        os.path.join(fsldir, "LICENSE.txt"),
    ]


def _freesurfer_candidates(context: dict) -> list:
    # The LEGAL license text shipped with FreeSurfer, never the user key file.
    fs_home = os.environ.get("FREESURFER_HOME", "")
    if not fs_home:
        return []
    return [
        os.path.join(fs_home, "LICENSE.txt"),
        os.path.join(fs_home, "LICENSE"),
        os.path.join(fs_home, "docs", "LICENSE.txt"),
    ]


def _slicer_candidates(context: dict) -> list:
    slicer_path = context.get("slicer_path", "")
    if not slicer_path:
        return []
    base = os.path.dirname(os.path.abspath(slicer_path))
    return [
        os.path.join(base, "License.txt"),
        os.path.join(base, "LICENSE.txt"),
        os.path.join(base, "share", "License.txt"),
    ]


def _dcm2niix_candidates(context: dict) -> list:
    # dcm2niix is typically a single binary with no local license file.
    return []


LICENSES = {
    FSL: LicenseInfo(
        tool_id=FSL,
        display_name="FSL (FMRIB Software Library)",
        official_url="https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html",
        is_html_online=True,
        installed_path_candidates=_fsl_candidates,
        bundled_filename="fsl.txt",
    ),
    FREESURFER: LicenseInfo(
        tool_id=FREESURFER,
        display_name="FreeSurfer",
        official_url="https://raw.githubusercontent.com/freesurfer/freesurfer/dev/LICENSE.txt",
        is_html_online=False,
        installed_path_candidates=_freesurfer_candidates,
        bundled_filename="freesurfer.txt",
    ),
    SLICER: LicenseInfo(
        tool_id=SLICER,
        display_name="3D Slicer",
        official_url="https://raw.githubusercontent.com/Slicer/Slicer/main/License.txt",
        is_html_online=False,
        installed_path_candidates=_slicer_candidates,
        bundled_filename="slicer.txt",
    ),
    DCM2NIIX: LicenseInfo(
        tool_id=DCM2NIIX,
        display_name="dcm2niix",
        official_url="https://raw.githubusercontent.com/rordenlab/dcm2niix/master/license.txt",
        is_html_online=False,
        installed_path_candidates=_dcm2niix_candidates,
        bundled_filename="dcm2niix.txt",
    ),
}
