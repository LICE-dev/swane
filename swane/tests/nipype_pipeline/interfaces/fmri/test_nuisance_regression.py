import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.interfaces.fmri.NuisanceRegression import NuisanceRegression


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    # The interface writes its outputs to the current directory.
    monkeypatch.chdir(tmp_path)


def _friston24(par_spm):
    d = np.diff(par_spm, axis=0, prepend=par_spm[:1])
    X = np.hstack([par_spm, d, par_spm**2, d**2])
    return X - X.mean(axis=0)


def _make_inputs(tmp_path, T=60, shape=(6, 6, 6), seed=0):
    rng = np.random.default_rng(seed)
    mask = np.zeros(shape, bool)
    mask[1:5, 1:5, 1:5] = True
    wm_roi = np.zeros(shape, bool)
    wm_roi[1:3, 1:3, 1:3] = True
    csf_roi = np.zeros(shape, bool)
    csf_roi[3:5, 3:5, 3:5] = True

    data = rng.standard_normal(shape + (T,))
    twin = rng.standard_normal(shape + (T,))
    par = rng.standard_normal((T, 6)) * 0.1  # SPM order [tx,ty,tz (mm), rx,ry,rz (rad)]

    paths = {}
    arrays = {
        "in_file": (data, np.float64),
        "twin_file": (twin, np.float64),
        "mask_file": (mask.astype(np.uint8), np.uint8),
        "wm_roi_file": (wm_roi.astype(np.uint8), np.uint8),
        "csf_roi_file": (csf_roi.astype(np.uint8), np.uint8),
    }
    for name, (arr, dtype) in arrays.items():
        p = tmp_path / f"{name}.nii.gz"
        nib.save(nib.Nifti1Image(arr.astype(dtype), np.eye(4)), p)
        paths[name] = str(p)

    par_path = tmp_path / "motion.par"
    np.savetxt(par_path, par)
    paths["par_file"] = str(par_path)

    return paths, data, twin, mask, wm_roi, csf_roi, par, T


def _expected_design(data, mask, wm_roi, csf_roi, T, par=None):
    trend = np.linspace(-1, 1, T)
    wm_ts = data[wm_roi].mean(axis=0)
    csf_ts = data[csf_roi].mean(axis=0)
    X = np.column_stack([trend, wm_ts, csf_ts])
    if par is not None:
        X = np.hstack([X, _friston24(par)])
    Xf = np.hstack([np.ones((T, 1)), X])
    return X, Xf


def _run(paths, motion24=False):
    interface = NuisanceRegression()
    interface.inputs.in_file = paths["in_file"]
    interface.inputs.twin_file = paths["twin_file"]
    interface.inputs.mask_file = paths["mask_file"]
    interface.inputs.wm_roi_file = paths["wm_roi_file"]
    interface.inputs.csf_roi_file = paths["csf_roi_file"]
    interface.inputs.motion24 = motion24
    if motion24:
        interface.inputs.par_file = paths["par_file"]
    return interface.run()


def test_residuals_orthogonal_to_every_design_column(tmp_path):
    paths, data, twin, mask, wm_roi, csf_roi, par, T = _make_inputs(tmp_path)
    result = _run(paths, motion24=False)

    X, _ = _expected_design(data, mask, wm_roi, csf_roi, T)

    for out_name in ("out_file", "twin_out_file"):
        res = nib.load(getattr(result.outputs, out_name)).get_fdata()[mask]  # (V, T)
        res_c = res - res.mean(axis=1, keepdims=True)
        res_std = res_c.std(axis=1, keepdims=True)
        res_std[res_std == 0] = 1
        Xc = X - X.mean(axis=0, keepdims=True)
        Xstd = Xc.std(axis=0, keepdims=True)
        corr = (res_c / res_std) @ (Xc / Xstd) / T  # (V, p)
        assert np.max(np.abs(corr)) < 1e-6


def test_rank_equals_p_plus_one(tmp_path):
    paths, data, twin, mask, wm_roi, csf_roi, par, T = _make_inputs(tmp_path)
    result = _run(paths, motion24=False)

    assert result.outputs.rank == 3 + 1  # trend, WM, CSF + constant


def test_twin_out_matches_manual_ols_with_same_x(tmp_path):
    paths, data, twin, mask, wm_roi, csf_roi, par, T = _make_inputs(tmp_path)
    result = _run(paths, motion24=False)

    _, Xf = _expected_design(data, mask, wm_roi, csf_roi, T)
    twin_masked = twin[mask]  # (V, T)
    mu = twin_masked.mean(axis=1, keepdims=True)
    beta = np.linalg.pinv(Xf) @ twin_masked.T  # (p+1, V)
    resid = twin_masked.T - Xf @ beta  # (T, V)
    expected = resid.T + mu  # (V, T)

    twin_out = nib.load(result.outputs.twin_out_file).get_fdata()[mask]
    np.testing.assert_allclose(twin_out, expected, atol=1e-4)


def test_motion24_increases_rank_by_24(tmp_path):
    paths, data, twin, mask, wm_roi, csf_roi, par, T = _make_inputs(tmp_path)

    baseline = _run(paths, motion24=False)
    with_motion = _run(paths, motion24=True)

    assert with_motion.outputs.rank - baseline.outputs.rank == 24


def test_empty_wm_roi_raises(tmp_path):
    """NuisanceRegression must raise a clear error when the WM ROI is empty."""
    paths, data, twin, mask, wm_roi, csf_roi, par, T = _make_inputs(tmp_path)

    # Overwrite WM ROI with an all-zero mask (empty ROI).
    empty = np.zeros(mask.shape, dtype=np.uint8)
    nib.save(nib.Nifti1Image(empty, np.eye(4)), paths["wm_roi_file"])

    with pytest.raises(ValueError, match="(?i)wm"):
        _run(paths, motion24=False)


def test_empty_csf_roi_raises(tmp_path):
    """NuisanceRegression must raise a clear error when the CSF ROI is empty."""
    paths, data, twin, mask, wm_roi, csf_roi, par, T = _make_inputs(tmp_path)

    # Overwrite CSF ROI with an all-zero mask (empty ROI).
    empty = np.zeros(mask.shape, dtype=np.uint8)
    nib.save(nib.Nifti1Image(empty, np.eye(4)), paths["csf_roi_file"])

    with pytest.raises(ValueError, match="(?i)csf"):
        _run(paths, motion24=False)
