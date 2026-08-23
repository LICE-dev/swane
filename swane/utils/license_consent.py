"""License text resolution and consent evaluation for external tools."""

import os
import urllib.request
from dataclasses import dataclass
from enum import Enum, auto

from swane.utils.LicenseReference import (
    LICENSES,
    LicenseInfo,
    bundled_license_path,
    FSL,
    FREESURFER,
    SLICER,
    DCM2NIIX,
)

UNKNOWN_VERSION = "unknown"


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


def _read_first_existing(candidates: list):
    for path in candidates:
        try:
            if path and os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    return fh.read(), path
        except OSError:
            continue
    return None


def fetch_online_license(url: str, is_html_online: bool, timeout: float = 8.0):
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


def resolve_license_text(info: LicenseInfo, context: dict, timeout: float = 8.0) -> ResolvedLicense:
    installed = _read_first_existing(info.installed_path_candidates(context))
    if installed is not None:
        return ResolvedLicense(info.tool_id, info.display_name, installed[0], False, LicenseSource.INSTALLED)

    online = fetch_online_license(info.official_url, info.is_html_online, timeout)
    if online is not None:
        return ResolvedLicense(info.tool_id, info.display_name, online[0], online[1], LicenseSource.ONLINE)

    with open(bundled_license_path(info), encoding="utf-8", errors="replace") as fh:
        bundled_text = fh.read()
    return ResolvedLicense(info.tool_id, info.display_name, bundled_text, False, LicenseSource.BUNDLED)
