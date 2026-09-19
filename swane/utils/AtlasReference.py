"""Static registry of the atlases/templates SWANe uses, for display only.

This mirrors the display-oriented purpose of ``LicenseReference.py``, but for
data rather than tools: it only points at license URLs to show on the Home
tab's Atlases column, and plays no part in the first-launch consent gate
(these are permissive/attribution-style licenses, not restrictive ones — see
``NOTICE.md``).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AtlasInfo:
    display_name: str
    license_url: str


ATLASES = (
    AtlasInfo(
        display_name="ICBM 2009c Nonlinear Symmetric Atlas",
        license_url="https://nist.mni.mcgill.ca/icbm-152-nonlinear-atlases-2009/",
    ),
    AtlasInfo(
        display_name="HCP842 whole-brain bundle atlas",
        license_url="https://creativecommons.org/licenses/by/4.0/",
    ),
    AtlasInfo(
        display_name="fsaverage",
        license_url="https://raw.githubusercontent.com/freesurfer/freesurfer/dev/LICENSE.txt",
    ),
    AtlasInfo(
        display_name="FLAT1 reference maps",
        license_url="https://github.com/LICE-dev/swane/blob/main/LICENSE",
    ),
)
