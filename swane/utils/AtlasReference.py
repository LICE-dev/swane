"""Static registry of the atlases/templates SWANe uses, for display only.

This mirrors the display-oriented purpose of ``LicenseReference.py``, but for
data rather than tools: it only points at license URLs to show on the Home
tab's Atlases column, and plays no part in the first-launch consent gate.
This is a display-only registry; the licenses it links to differ from one
another (some permissive, some non-commercial) — see ``NOTICE.md``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AtlasInfo:
    display_name: str
    license_url: str


ATLASES = (
    AtlasInfo(
        display_name="TemplateFlow MNI152NLin2009c Atlases (Symmetric & Asymmetric)",
        license_url="https://nist.mni.mcgill.ca/icbm-152-nonlinear-atlases-2009/",
    ),
    AtlasInfo(
        display_name="TemplateFlow MNI152NLin6Asym (FSL MNI152)",
        license_url="https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html",
    ),
    AtlasInfo(
        display_name="HCP842 whole-brain bundle atlas",
        license_url="https://creativecommons.org/licenses/by/4.0/",
    ),
    AtlasInfo(
        display_name="fsaverage",
        license_url="https://raw.githubusercontent.com/freesurfer/freesurfer/dev/LICENSE.txt",
    ),
)
