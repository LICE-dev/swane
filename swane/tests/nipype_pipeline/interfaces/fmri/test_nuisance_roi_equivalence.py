"""Equivalence: niimath ROI chain vs the old NuisanceRoi formula.

The old formula: (subject > 0.5) & (prior > 0.5) & mask, dtype uint8.
The new niimath chain: prior -thr 0.5 -bin -mas mask → prior_roi;
    subject -thr 0.5 -bin -mas prior_roi → roi.
niimath's -thr keeps values ≥ 0.5 (not strictly > 0.5); on interpolated
values this difference is negligible.  The test uses values away from
exactly 0.5 so the two formulas agree exactly.
"""

import numpy as np
import nibabel as nib
import pytest
import os


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _save(path, data, affine=np.eye(4)):
    nib.save(nib.Nifti1Image(data.astype(np.float32), affine), str(path))
    return str(path)


def _old_formula(subject, prior, mask, thr=0.5):
    """Reference: the old NuisanceRoi logic (strict > thr)."""
    return ((subject > thr) & (prior > thr) & (mask > 0)).astype(np.uint8)


def test_niimath_chain_matches_old_formula(tmp_path):
    """On synthetic data with values away from exactly 0.5, the niimath chain
    gives the same mask as the old NuisanceRoi formula."""
    from swane.nipype_pipeline.interfaces.niimath import ImageMaths

    rng = np.random.default_rng(42)
    shape = (8, 8, 8)

    # Subject: values drawn from {0.0, 0.3, 0.7, 0.9} — none at exactly 0.5.
    subject = rng.choice([0.0, 0.3, 0.7, 0.9], size=shape).astype(np.float32)

    # Prior: similarly away from 0.5.
    prior = rng.choice([0.0, 0.2, 0.6, 0.8], size=shape).astype(np.float32)

    # Mask: binary.
    mask = np.zeros(shape, dtype=np.uint8)
    mask[1:7, 1:7, 1:7] = 1

    subject_file = _save(tmp_path / "subject.nii.gz", subject)
    prior_file = _save(tmp_path / "prior.nii.gz", prior)
    mask_file = _save(tmp_path / "mask.nii.gz", mask)

    # --- Step 1: prior -thr 0.5 -bin -mas mask ---
    prior_thr = ImageMaths()
    prior_thr.inputs.in_file = prior_file
    prior_thr.inputs.op_string = "-thr 0.5 -bin -mas"
    prior_thr.inputs.in_file2 = mask_file
    prior_thr.inputs.out_data_type = "char"
    prior_thr.inputs.suffix = "_prior_thr"
    prior_res = prior_thr.run()
    prior_roi_file = prior_res.outputs.out_file

    # --- Step 2: subject -thr 0.5 -bin -mas prior_roi ---
    roi_node = ImageMaths()
    roi_node.inputs.in_file = subject_file
    roi_node.inputs.op_string = "-thr 0.5 -bin -mas"
    roi_node.inputs.in_file2 = prior_roi_file
    roi_node.inputs.out_data_type = "char"
    roi_node.inputs.suffix = "_roi"
    roi_res = roi_node.run()

    niimath_roi = nib.load(roi_res.outputs.out_file).get_fdata()
    reference = _old_formula(subject, prior, mask)

    np.testing.assert_array_equal(niimath_roi.astype(np.uint8), reference)
    assert niimath_roi.sum() > 0, "Test fixture must have non-empty ROI"
