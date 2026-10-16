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
NIIMATH = "niimath"
NILEARN = "nilearn"
TOOL_IDS = (
    FSL,
    FREESURFER,
    SLICER,
    DCM2NIIX,
    ANTSPYX,
    ANTSPYNET,
    DIPY,
    NIIMATH,
    NILEARN,
)

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


def _dist_info_license_candidates(package_name: str) -> list:
    """
    Fast resolution of license file paths for an installed pip package.

    Directly inspects the package's .dist-info/ directory (and .dist-info/licenses/
    per PEP 639) without loading dist.files or scanning all installed package files.
    """
    try:
        from importlib.metadata import distribution, PackageNotFoundError
    except ImportError:
        return []
    try:
        dist = distribution(package_name)
    except PackageNotFoundError:
        return []

    candidates = []
    dist_path = getattr(dist, "_path", None)
    if dist_path is not None and dist_path.is_dir():
        for entry in dist_path.iterdir():
            try:
                if not entry.is_file():
                    continue
            except OSError:
                continue
            name_lower = entry.name.lower()
            if name_lower.startswith("licen") or name_lower.startswith("copying"):
                candidates.append(str(entry))
        licenses_dir = dist_path / "licenses"
        if licenses_dir.is_dir():
            for entry in licenses_dir.iterdir():
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                name_lower = entry.name.lower()
                if name_lower.startswith("licen") or name_lower.startswith("copying"):
                    candidates.append(str(entry))
        if candidates:
            return candidates

    # Fallback path if dist._path is unavailable or yielded nothing: filter dist.files
    for entry in dist.files or []:
        parts = [p.lower() for p in entry.parts]
        name_lower = entry.name.lower()
        if ("licenses" in parts or any(p.endswith(".dist-info") for p in parts)) and (
            name_lower.startswith("licen") or name_lower.startswith("copying")
        ):
            try:
                candidates.append(str(dist.locate_file(entry)))
            except Exception:
                continue
    return candidates


def _dcm2niix_candidates(context: dict) -> list:
    return _dist_info_license_candidates("dcm2niix")


def _antspyx_candidates(context: dict) -> list:
    return _dist_info_license_candidates("antspyx")


def _niimath_candidates(context: dict) -> list:
    return _dist_info_license_candidates("niimath")


def _nilearn_candidates(context: dict) -> list:
    return _dist_info_license_candidates("nilearn")


def _dipy_candidates(context: dict) -> list:
    return _dist_info_license_candidates("dipy")


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
    NIIMATH: LicenseInfo(
        tool_id=NIIMATH,
        display_name="niimath",
        official_url="https://raw.githubusercontent.com/rordenlab/niimath/master/LICENSE",
        is_html_online=False,
        installed_path_candidates=_niimath_candidates,
        bundled_filename="niimath.txt",
        online_is_official=True,
    ),
    NILEARN: LicenseInfo(
        tool_id=NILEARN,
        display_name="nilearn",
        official_url="https://raw.githubusercontent.com/nilearn/nilearn/main/LICENSE",
        is_html_online=False,
        installed_path_candidates=_nilearn_candidates,
        bundled_filename="nilearn.txt",
    ),
}
