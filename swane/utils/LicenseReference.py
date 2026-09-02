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
ANTSPYX = "antspyx"
ANTSPYNET = "antspynet"
DIPY = "dipy"
TOOL_IDS = (FSL, FREESURFER, SLICER, DCM2NIIX, ANTSPYX, ANTSPYNET, DIPY)

_BUNDLED_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "licenses"
)


@dataclass(frozen=True)
class LicenseInfo:
    tool_id: str
    display_name: str
    official_url: str
    is_html_online: bool
    installed_path_candidates: Callable[[dict], list]
    bundled_filename: str
    # When True, the online source IS the official reference for this tool (e.g.
    # the project repository the app itself links to), so falling back to it is
    # normal and must not raise a "installed not found" warning in the gate.
    online_is_official: bool = False


def bundled_license_path(info: "LicenseInfo") -> str:
    return os.path.normpath(os.path.join(_BUNDLED_DIR, info.bundled_filename))


def _fsl_candidates(context: dict) -> list:
    fsldir = os.environ.get("FSLDIR", "")
    if not fsldir:
        return []
    return [
        # Real filename shipped by FSL (British spelling, .FSL extension).
        os.path.join(fsldir, "LICENCE.FSL"),
        os.path.join(fsldir, "LICENSE.FSL"),
        os.path.join(fsldir, "LICENCE"),
        os.path.join(fsldir, "LICENSE"),
        os.path.join(fsldir, "LICENSE.txt"),
    ]


def _freesurfer_candidates(context: dict) -> list:
    # The LEGAL license agreement (SLA) shipped with FreeSurfer, never the
    # per-user registration key file (license.txt / .license / _license.txt).
    # Use exact filenames: FREESURFER_HOME contains many other files whose name
    # includes "license" (component/third-party licenses).
    fs_home = os.environ.get("FREESURFER_HOME", "")
    if not fs_home:
        return []
    return [
        # Real filename shipped by FreeSurfer: the Software License Agreement.
        os.path.join(fs_home, "docs", "license.freesurfer_SLA.txt"),
        os.path.join(fs_home, "license.freesurfer_SLA.txt"),
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
    # The dcm2niix pip package (a SWANe dependency) ships its license under the
    # distribution's .dist-info/licenses/ directory (PEP 639); recover it from
    # the installed package so the displayed text matches the installed version.
    try:
        from importlib.metadata import distribution, PackageNotFoundError
    except ImportError:
        return []
    try:
        dist = distribution("dcm2niix")
    except PackageNotFoundError:
        return []
    candidates = []
    for entry in dist.files or []:
        parts = [part.lower() for part in entry.parts]
        if "licenses" in parts and entry.name.lower().startswith("licen"):
            try:
                candidates.append(str(dist.locate_file(entry)))
            except Exception:
                continue
    return candidates


def _antspyx_candidates(context: dict) -> list:
    # The antspyx pip package (a SWANe dependency, imported as "ants") ships its
    # license under the distribution's .dist-info/licenses/ directory (PEP 639);
    # recover it from the installed package so the displayed text matches the
    # installed version.
    try:
        from importlib.metadata import distribution, PackageNotFoundError
    except ImportError:
        return []
    try:
        dist = distribution("antspyx")
    except PackageNotFoundError:
        return []
    candidates = []
    for entry in dist.files or []:
        parts = [part.lower() for part in entry.parts]
        if "licenses" in parts and entry.name.lower().startswith("licen"):
            try:
                candidates.append(str(dist.locate_file(entry)))
            except Exception:
                continue
    return candidates


def _dipy_candidates(context: dict) -> list:
    # The dipy pip package (a SWANe dependency) ships its license directly
    # under the distribution's .dist-info/ directory, rather than the PEP 639
    # licenses/ subdirectory dcm2niix/antspyx use; recover it from the
    # installed package so the displayed text matches the installed version.
    try:
        from importlib.metadata import distribution, PackageNotFoundError
    except ImportError:
        return []
    try:
        dist = distribution("dipy")
    except PackageNotFoundError:
        return []
    candidates = []
    for entry in dist.files or []:
        if entry.name.lower().startswith("licen"):
            try:
                candidates.append(str(dist.locate_file(entry)))
            except Exception:
                continue
    return candidates


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
        # 3D Slicer does not ship a discoverable local license file; its GUI
        # points to this same repository file, so online is the official source.
        online_is_official=True,
    ),
    DCM2NIIX: LicenseInfo(
        tool_id=DCM2NIIX,
        display_name="dcm2niix",
        official_url="https://raw.githubusercontent.com/rordenlab/dcm2niix/master/license.txt",
        is_html_online=False,
        installed_path_candidates=_dcm2niix_candidates,
        bundled_filename="dcm2niix.txt",
    ),
    ANTSPYX: LicenseInfo(
        tool_id=ANTSPYX,
        display_name="ANTs (antspyx)",
        official_url="https://raw.githubusercontent.com/ANTsX/ANTsPy/main/LICENSE",
        is_html_online=False,
        installed_path_candidates=_antspyx_candidates,
        bundled_filename="antspyx.txt",
    ),
    # antspynet has no installed license candidates: it ships no LICENSE file
    # inside its distribution, so this always falls back to the online/bundled
    # copy. Note the downloaded pretrained model weights carry their own
    # upstream terms, separate from the antspynet package's Apache-2.0 license.
    ANTSPYNET: LicenseInfo(
        tool_id=ANTSPYNET,
        display_name="ANTsPyNet",
        official_url="https://raw.githubusercontent.com/ANTsX/ANTsPyNet/main/LICENSE.md",
        is_html_online=False,
        installed_path_candidates=lambda context: [],
        bundled_filename="antspynet_license.txt",
        online_is_official=True,
    ),
    DIPY: LicenseInfo(
        tool_id=DIPY,
        display_name="dipy",
        official_url="https://raw.githubusercontent.com/dipy/dipy/master/LICENSE",
        is_html_online=False,
        installed_path_candidates=_dipy_candidates,
        bundled_filename="dipy.txt",
    ),
}
