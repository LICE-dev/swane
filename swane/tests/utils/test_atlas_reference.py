"""Unit tests for :mod:`swane.utils.AtlasReference`."""

from swane.utils.AtlasReference import ATLASES


def test_mni152nlin2009c_row_names_only_the_2009c_templates():
    names = [atlas.display_name for atlas in ATLASES]
    assert "TemplateFlow MNI152NLin2009c Atlases (Symmetric & Asymmetric)" in names
    # The old combined display name must be gone: it used to cover both the
    # 2009c and the NLin6Asym templates under a single McGill license link.
    assert "TemplateFlow MNI152 Atlases (Symmetric & Asymmetric)" not in names


def test_mni152nlin2009c_row_links_to_mcgill_icbm_license():
    row = next(
        atlas
        for atlas in ATLASES
        if atlas.display_name
        == "TemplateFlow MNI152NLin2009c Atlases (Symmetric & Asymmetric)"
    )
    assert (
        row.license_url == "https://nist.mni.mcgill.ca/icbm-152-nonlinear-atlases-2009/"
    )


def test_mni152nlin6asym_row_is_listed_under_the_fsl_license():
    row = next(
        atlas
        for atlas in ATLASES
        if atlas.display_name == "TemplateFlow MNI152NLin6Asym (FSL MNI152)"
    )
    assert row.license_url == "https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html"


def test_unrelated_atlas_rows_are_unchanged():
    names = {atlas.display_name for atlas in ATLASES}
    assert "HCP842 whole-brain bundle atlas" in names
    assert "fsaverage" in names
