import numpy as np
import nibabel as nib
import pytest
from scipy import ndimage

from swane.nipype_pipeline.interfaces.fmri.MaskedResampleCombine import (
    MaskedResampleCombine,
)

NATIVE = (12, 12, 12)
ZOOM = 3  # native 3 mm -> reference 1 mm


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    # The interface writes its output in the current directory.
    monkeypatch.chdir(tmp_path)


def _save(tmp_path, name, data):
    path = tmp_path / name
    nib.save(nib.Nifti1Image(data.astype(np.float32), np.eye(4)), path)
    return str(path)


def _resample(vol):
    # Linear resampling onto a 3x finer grid (the reference space).
    return ndimage.zoom(vol.astype(np.float64), ZOOM, order=1)


def _native_fixture(sign=1.0):
    """z = 3 inside a surviving block and 1 elsewhere; the survivor mask is
    the block itself (the native decision)."""
    block = np.zeros(NATIVE, bool)
    block[4:8, 4:8, 4:8] = True
    z = np.where(block, 3.0, 1.0) * sign
    return z, block


def _run(tmp_path, z_ref, pos_ref, neg_ref, **inputs):
    iface = MaskedResampleCombine()
    iface.inputs.z_file = _save(tmp_path, "z.nii.gz", z_ref)
    iface.inputs.pos_mask_file = _save(tmp_path, "pos.nii.gz", pos_ref)
    iface.inputs.neg_mask_file = _save(tmp_path, "neg.nii.gz", neg_ref)
    for key, value in inputs.items():
        setattr(iface.inputs, key, value)
    res = iface.run()
    return res.outputs.out_file, nib.load(res.outputs.out_file).get_fdata()


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_no_sub_threshold_ramp(tmp_path, sign):
    z, block = _native_fixture(sign)
    pos = block & (z > 0)
    neg = block & (z < 0)
    z_ref, pos_ref, neg_ref = _resample(z), _resample(pos), _resample(neg)

    _, out = _run(tmp_path, z_ref, pos_ref, neg_ref)

    block_ref = _resample(block) > 0.5
    interior = ndimage.binary_erosion(block_ref, iterations=2)
    dilated = ndimage.binary_dilation(block_ref, iterations=2)
    nonzero = out != 0
    # No sub-threshold value inside the block and no value outside it.
    assert not np.any(nonzero & (np.abs(out) < 1.95))
    assert np.all(np.abs(out[interior]) >= 1.95)
    assert not np.any(nonzero & ~dilated)
    assert np.all(np.sign(out[nonzero]) == sign)
    # Values are the resampled continuous z, not a mask.
    np.testing.assert_allclose(out[nonzero], z_ref[nonzero])

    # The fixture does expose the ramp that linear resampling of the
    # thresholded map produces.
    thresholded_ref = _resample(np.where(block, z, 0.0))
    ramp = (thresholded_ref != 0) & (np.abs(thresholded_ref) < 1.95)
    assert np.any(ramp)


def test_sign_rule(tmp_path):
    z_ref = np.array([2.5, -2.5, 2.5, -2.5, 2.5, 0.0], np.float64).reshape(6, 1, 1)
    pos_ref = np.array([0.9, 0.9, 0.4, 0.0, 0.0, 0.9]).reshape(6, 1, 1)
    neg_ref = np.array([0.0, 0.0, 0.0, 0.9, 0.9, 0.9]).reshape(6, 1, 1)
    _, out = _run(tmp_path, z_ref, pos_ref, neg_ref)
    np.testing.assert_allclose(out.ravel(), [2.5, 0.0, 0.0, -2.5, 0.0, 0.0])


def test_out_file_name_and_header(tmp_path):
    z_ref = np.full((3, 3, 3), 2.0)
    pos_ref = np.ones((3, 3, 3))
    neg_ref = np.zeros((3, 3, 3))
    path, out = _run(
        tmp_path, z_ref, pos_ref, neg_ref, out_file="r-thresh_zstat01.nii.gz"
    )
    assert path == str(tmp_path / "r-thresh_zstat01.nii.gz")
    assert nib.load(path).get_data_dtype() == np.dtype(np.float32)
    np.testing.assert_allclose(out, 2.0)


def test_mask_thr(tmp_path):
    z_ref = np.full((2, 1, 1), 3.0)
    pos_ref = np.array([0.6, 0.8]).reshape(2, 1, 1)
    neg_ref = np.zeros((2, 1, 1))
    _, out = _run(tmp_path, z_ref, pos_ref, neg_ref, mask_thr=0.7)
    np.testing.assert_allclose(out.ravel(), [0.0, 3.0])
