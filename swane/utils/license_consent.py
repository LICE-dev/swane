"""License text resolution and consent evaluation for external tools."""

import os
import urllib.request
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from swane.utils.LicenseReference import (
    LICENSES,
    LicenseInfo,
    bundled_license_path,
    FSL,
    FREESURFER,
    SLICER,
    DCM2NIIX,
    ANTSPYX,
    ANTSPYNET,
)

UNKNOWN_VERSION = "unknown"
DEFAULT_LICENSE_FETCH_TIMEOUT = 3.0


class LicenseSource(Enum):
    INSTALLED = auto()
    ONLINE = auto()
    BUNDLED = auto()


@dataclass
class ResolvedLicense:
    tool_id: str
    display_name: str
    text: str
    is_html: bool
    source: LicenseSource
    # Whether the gate should warn that this text is not the user's installed
    # copy. False when the source is the tool's official reference anyway.
    show_source_warning: bool = True


def _read_first_existing(candidates: list):
    for path in candidates:
        try:
            if path and os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    return fh.read(), path
        except OSError:
            continue
    return None


def fetch_online_license(
    url: str,
    is_html_online: bool,
    timeout: float = DEFAULT_LICENSE_FETCH_TIMEOUT,
):
    """Fetch license text online. Return (text, is_html) or None on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        return None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None
    if not text.strip():
        return None
    return text, is_html_online


def resolve_license_text(
    info: LicenseInfo,
    context: dict,
    timeout: float = DEFAULT_LICENSE_FETCH_TIMEOUT,
) -> ResolvedLicense:
    installed = _read_first_existing(info.installed_path_candidates(context))
    if installed is not None:
        return ResolvedLicense(
            info.tool_id,
            info.display_name,
            installed[0],
            False,
            LicenseSource.INSTALLED,
            show_source_warning=False,
        )

    online = fetch_online_license(info.official_url, info.is_html_online, timeout)
    if online is not None:
        return ResolvedLicense(
            info.tool_id,
            info.display_name,
            online[0],
            online[1],
            LicenseSource.ONLINE,
            show_source_warning=not info.online_is_official,
        )

    with open(bundled_license_path(info), encoding="utf-8", errors="replace") as fh:
        bundled_text = fh.read()
    return ResolvedLicense(
        info.tool_id,
        info.display_name,
        bundled_text,
        False,
        LicenseSource.BUNDLED,
        show_source_warning=True,
    )


def local_license_path(info: LicenseInfo, context: dict):
    """
    Return the first existing local license file for a tool, or None.

    Only references the legal license text (never a per-user key file), because
    the candidate lists are defined that way.
    """
    for path in info.installed_path_candidates(context):
        try:
            if path and os.path.isfile(path):
                return path
        except OSError:
            continue
    return None


def version_with_license(tool_id: str, version, context: dict = None) -> str:
    """
    Return a version string with an inline license link appended.

    Used to place a license link inside the version parenthesis of a dependency
    label. When there is no version (the tool/dependency was not found) the
    value is returned unchanged and no license link is shown.
    """
    if not version:
        return version
    from swane import strings

    url = license_link_url(LICENSES[tool_id], context or {})
    return '%s - <a href="%s">%s</a>' % (
        version,
        url,
        strings.mainwindow_home_license_link,
    )


def license_link_url(info: LicenseInfo, context: dict) -> str:
    """
    Return a URL to open for a tool's license.

    The local installed license file when present (as a file:// URL), otherwise
    the tool's official license URL.
    """
    local = local_license_path(info, context)
    if local is not None:
        return Path(os.path.abspath(local)).as_uri()
    return info.official_url


def _fsl_version():
    from nipype.interfaces import fsl

    return fsl.base.Info.version()


def _freesurfer_version():
    from nipype.interfaces import freesurfer

    if freesurfer.base.Info.version() is None:
        return None
    return str(freesurfer.base.Info.looseversion())


def _dcm2niix_version():
    from nipype.interfaces import dcm2nii

    value = dcm2nii.Info.version()
    return None if value is None else str(value)


def _antspyx_version():
    try:
        import ants

        return str(ants.__version__)
    except Exception:
        return None


def _antspynet_version():
    try:
        import importlib.metadata

        return importlib.metadata.version("antspynet")
    except Exception:
        return None


def _is_slicer_detected(config) -> bool:
    from swane.utils.DependencyManager import DependencyManager

    return DependencyManager.is_slicer(config)


def _norm(value) -> str:
    value = "" if value is None else str(value).strip()
    return value if value else UNKNOWN_VERSION


def _cached_dependency_version(dependency_manager, attribute: str, resolver):
    dependence = getattr(dependency_manager, attribute, None)
    detected_version = getattr(dependence, "detected_version", None)
    return resolver() if detected_version is None else detected_version


def detected_tool_versions(dependency_manager, config) -> dict:
    """Return {tool_id: detected_version_or_UNKNOWN} for each detected tool."""
    versions = {}
    if dependency_manager.is_fsl():
        versions[FSL] = _norm(
            _cached_dependency_version(dependency_manager, "fsl", _fsl_version)
        )
    if dependency_manager.is_freesurfer():
        versions[FREESURFER] = _norm(
            _cached_dependency_version(
                dependency_manager, "freesurfer", _freesurfer_version
            )
        )
    if _is_slicer_detected(config):
        versions[SLICER] = _norm(config.get_slicer_version())
    if dependency_manager.is_dcm2niix():
        versions[DCM2NIIX] = _norm(_dcm2niix_version())
    if dependency_manager.is_antspyx():
        versions[ANTSPYX] = _norm(
            _cached_dependency_version(dependency_manager, "antspyx", _antspyx_version)
        )
    if dependency_manager.is_antspynet():
        versions[ANTSPYNET] = _norm(_antspynet_version())
    return versions


def tools_needing_consent(
    dependency_manager, config, detected_versions: dict = None
) -> list:
    """Detected tools whose accepted version differs from the detected version.

    ``detected_versions`` accepts a startup snapshot so callers can compare and
    later persist exactly the same versions without probing external tools
    multiple times.
    """
    detected = (
        detected_tool_versions(dependency_manager, config)
        if detected_versions is None
        else detected_versions
    )
    ordered = [FSL, FREESURFER, SLICER, DCM2NIIX, ANTSPYX, ANTSPYNET]
    needing = []
    for tool_id in ordered:
        if tool_id not in detected:
            continue
        if config.get_accepted_license_version(tool_id) != detected[tool_id]:
            needing.append(tool_id)
    return needing
