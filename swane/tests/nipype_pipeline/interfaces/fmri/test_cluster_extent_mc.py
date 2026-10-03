import json

import nibabel as nib
import numpy as np
import pytest
from scipy import ndimage

from swane.nipype_pipeline.interfaces.fmri import ClusterExtentMC as cmc
from swane.nipype_pipeline.interfaces.fmri.ClusterExtentMC import (
    FWHM_PER_B,
    ClusterExtentMC,
    empirical_acf,
    fit_acf,
    mc_k,
    null_fields,
)

VOXEL_MM = 3.0
ZOOMS = (VOXEL_MM,) * 3


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    # The interface writes its outputs in the current directory.
    monkeypatch.chdir(tmp_path)


def _ellipsoid_mask(shape, radii):
    grid = np.meshgrid(*[np.arange(n) - (n - 1) / 2 for n in shape], indexing="ij")
    return sum((g / r) ** 2 for g, r in zip(grid, radii)) <= 1.0


def _smooth_residuals(dmask, fwhm_mm, n_vol, seed):
    """Residual volumes with a Gaussian spatial ACF of the given FWHM,
    generated independently of the module: white noise convolved with a
    Gaussian kernel of sigma = sigma_acf / sqrt(2), on a padded grid."""
    sigma_vox = fwhm_mm / FWHM_PER_B / np.sqrt(2) / VOXEL_MM
    pad = int(np.ceil(4 * sigma_vox))
    rng = np.random.default_rng(seed)
    shape = tuple(s + 2 * pad for s in dmask.shape)
    crop = tuple(slice(pad, pad + s) for s in dmask.shape)
    vols = [
        ndimage.gaussian_filter(rng.standard_normal(shape), sigma_vox)[crop][dmask]
        for _ in range(n_vol)
    ]
    return np.stack(vols, axis=1)  # (V, T)


def _save_inputs(tmp_path, dmask, R_vt, tag):
    affine = np.diag([VOXEL_MM, VOXEL_MM, VOXEL_MM, 1.0])
    mask_file = tmp_path / f"mask_{tag}.nii.gz"
    nib.save(nib.Nifti1Image(dmask.astype(np.uint8), affine), mask_file)
    vol = np.zeros(dmask.shape + (R_vt.shape[1],), np.float32)
    vol[dmask] = R_vt
    res_file = tmp_path / f"res_{tag}.nii.gz"
    nib.save(nib.Nifti1Image(vol, affine), res_file)
    return str(res_file), str(mask_file)


def _run(res_file, mask_file, **inputs):
    node = ClusterExtentMC()
    node.inputs.residual_file = res_file
    node.inputs.mask_file = mask_file
    for name, value in inputs.items():
        setattr(node.inputs, name, value)
    return node.run()


def _simulator_check(dmask, n_fields):
    """Fields with a pure Gaussian ACF (a = 1) of FWHM 2 and 3 voxels must
    give back the FWHM within 10 % with a >= 0.9."""
    out = {}
    for fw_vox in (2.0, 3.0):
        fw = fw_vox * VOXEL_MM
        b = fw / FWHM_PER_B
        R = np.stack(list(null_fields(1.0, b, 1.0, dmask, ZOOMS, n_fields, seed=1)), 1)
        (a_hat, b_hat, _), _ = fit_acf(*empirical_acf(R, dmask, ZOOMS))
        out[fw] = (FWHM_PER_B * b_hat, a_hat)
    return out


def test_simulator_check_recovers_gaussian_fwhm():
    # Brain-sized mask on a 3 mm grid, 40 fields per FWHM (about 2 s).
    dmask = _ellipsoid_mask((56, 64, 48), (25, 30, 22))
    assert dmask.sum() > 60000
    res = _simulator_check(dmask, 40)
    for fw, (fw_hat, a_hat) in res.items():
        assert abs(fw_hat - fw) / fw <= 0.10, (fw, fw_hat)
        assert a_hat >= 0.9, (fw, a_hat)


def test_acf_fit_recovers_independently_smoothed_residuals():
    dmask = _ellipsoid_mask((34, 38, 30), (15, 17, 13))
    R = _smooth_residuals(dmask, 9.0, 30, seed=5)
    (a_hat, b_hat, _), rmse = fit_acf(*empirical_acf(R, dmask, ZOOMS))
    assert abs(FWHM_PER_B * b_hat - 9.0) / 9.0 <= 0.10
    assert a_hat >= 0.9
    assert rmse < 0.02


def test_k_grows_with_smoothness(tmp_path):
    dmask = _ellipsoid_mask((30, 34, 26), (13, 15, 11))
    ks = {}
    for fwhm in (6.0, 9.0):
        R = _smooth_residuals(dmask, fwhm, 30, seed=7)
        res_file, mask_file = _save_inputs(tmp_path, dmask, R, f"fw{fwhm:.0f}")
        result = _run(res_file, mask_file, n_sim=200)
        ks[fwhm] = result.outputs.min_cluster_voxels
        report = json.load(open(result.outputs.report_file))
        assert report["min_cluster_voxels"] == ks[fwhm]
        assert abs(report["fwhm_gauss_mm"] - fwhm) / fwhm <= 0.15
        for key in (
            "a",
            "b_mm",
            "c_mm",
            "rmse",
            "max_cluster_median",
            "max_cluster_p95",
        ):
            assert np.isfinite(report[key]), key
        assert report["acf_model"] == "fitted"
    assert ks[9.0] > ks[6.0] >= 1


def test_same_random_state_gives_same_k(tmp_path):
    dmask = _ellipsoid_mask((24, 26, 22), (10, 11, 9))
    R = _smooth_residuals(dmask, 6.0, 20, seed=3)
    res_file, mask_file = _save_inputs(tmp_path, dmask, R, "det")
    k1 = _run(res_file, mask_file, n_sim=100, random_state=4).outputs
    k2 = _run(res_file, mask_file, n_sim=100, random_state=4).outputs
    assert k1.min_cluster_voxels == k2.min_cluster_voxels
    assert (
        json.load(open(k1.report_file))["max_cluster_p95"]
        == json.load(open(k2.report_file))["max_cluster_p95"]
    )


def test_lags_with_too_few_voxel_pairs_are_skipped():
    # A cube of side 12 voxels: a lag (dx, dy, dz) has
    # (12-|dx|)(12-|dy|)(12-|dz|) voxel pairs inside the mask.
    side = 12
    dmask = np.zeros((20, 20, 20), bool)
    dmask[4:16, 4:16, 4:16] = True
    lags = np.array(np.meshgrid(*[np.arange(side)] * 3, indexing="ij")).reshape(3, -1)
    pairs = np.prod(side - lags, axis=0)
    dist = np.sqrt((lags**2).sum(0))
    longest_kept = dist[pairs > 1000].max()
    assert longest_kept == 5.0  # (5, 0, 0): 1008 pairs; (6, 0, 0): 864
    R = np.random.default_rng(0).standard_normal((int(dmask.sum()), 10))

    rc, vc = empirical_acf(R, dmask, (1.0, 1.0, 1.0), min_pairs=1000)
    assert 4.0 < rc.max() <= longest_kept
    assert np.all(np.isfinite(vc))

    rc_all, _ = empirical_acf(R, dmask, (1.0, 1.0, 1.0), min_pairs=0)
    assert rc_all.max() > 10.0


def test_all_zero_residuals_fall_back_to_independent_voxels(tmp_path):
    dmask = _ellipsoid_mask((20, 22, 18), (8, 9, 7))
    R = np.zeros((int(dmask.sum()), 12))
    res_file, mask_file = _save_inputs(tmp_path, dmask, R, "zero")
    result = _run(res_file, mask_file, n_sim=100)
    k = result.outputs.min_cluster_voxels
    report = json.load(open(result.outputs.report_file))
    assert isinstance(k, int) and k >= 1
    assert report["acf_model"] == "empirical"
    assert "fit_error" in report
    # No measurable correlation: white-noise null, only a few voxels per
    # largest cluster at |z| > 1.95.
    assert k <= 10


def test_failed_fit_falls_back_to_the_empirical_acf(tmp_path, monkeypatch):
    dmask = _ellipsoid_mask((26, 28, 24), (11, 12, 10))
    R = _smooth_residuals(dmask, 9.0, 20, seed=11)
    res_file, mask_file = _save_inputs(tmp_path, dmask, R, "fail")
    k_fit = _run(res_file, mask_file, n_sim=200).outputs.min_cluster_voxels

    def _raise(*args, **kwargs):
        raise RuntimeError("Optimal parameters not found")

    monkeypatch.setattr(cmc, "curve_fit", _raise)
    result = _run(res_file, mask_file, n_sim=200)
    report = json.load(open(result.outputs.report_file))
    assert report["acf_model"] == "empirical"
    assert "Optimal parameters not found" in report["fit_error"]
    k_emp = result.outputs.min_cluster_voxels
    assert 0.5 * k_fit <= k_emp <= 2.0 * k_fit


def test_mc_k_is_defined_when_no_null_field_has_a_cluster():
    # A one-voxel mask: every spatially standardised field is 0 (NaN guarded)
    # and no voxel crosses the threshold, so k is the smallest size, 1.
    dmask = np.zeros((5, 5, 5), bool)
    dmask[2, 2, 2] = True
    k, info = mc_k(1.0, 1.0, 1.0, dmask, ZOOMS, n=20)
    assert k == 1
    assert info["max_cluster_p95"] == 0
