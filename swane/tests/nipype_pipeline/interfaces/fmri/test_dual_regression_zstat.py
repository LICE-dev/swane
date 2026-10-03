import os
import numpy as np
import nibabel as nib
import pytest
from scipy import special, stats
from swane.nipype_pipeline.interfaces.fmri.DualRegressionZStat import (
    DualRegressionZStat,
    _t_logsf_series,
    t_to_z,
)


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    # The interface writes its outputs in the current directory.
    monkeypatch.chdir(tmp_path)


def _make_inputs(tmp_path, T=60, V_shape=(5, 5, 5), K=2, seed=0):
    rng = np.random.RandomState(seed)
    preproc_file = tmp_path / "preproc.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"
    components_file = tmp_path / "components.nii.gz"

    data = rng.randn(*V_shape, T)
    nib.save(nib.Nifti1Image(data, np.eye(4)), preproc_file)

    mask = np.zeros(V_shape)
    mask[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    comps = rng.randn(*V_shape, K)
    comps[~mask.astype(bool)] = 0
    nib.save(nib.Nifti1Image(comps, np.eye(4)), components_file)

    return str(preproc_file), str(mask_file), str(components_file), T, K


def _run(preproc_file, mask_file, components_file, **inputs):
    interface = DualRegressionZStat()
    interface.inputs.preproc_file = preproc_file
    interface.inputs.mask_file = mask_file
    interface.inputs.components_file = components_file
    for name, value in inputs.items():
        setattr(interface.inputs, name, value)
    return interface.run()


def _zstat(result):
    return nib.load(result.outputs.zstat_file).get_fdata()


def test_dual_regression_zstat(tmp_path):
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path)

    result = _run(preproc_file, mask_file, components_file)

    assert os.path.exists(result.outputs.zstat_file)
    assert os.path.exists(result.outputs.ic_mix)
    assert os.path.exists(result.outputs.ic_ft_mix)
    assert os.path.exists(result.outputs.residual_file)
    assert os.path.dirname(result.outputs.zstat_file) == str(tmp_path)

    z_img = nib.load(result.outputs.zstat_file)
    assert z_img.shape == (5, 5, 5, K)

    ic_mix = np.loadtxt(result.outputs.ic_mix)
    assert ic_mix.shape == (T, K)

    ic_ft_mix = np.loadtxt(result.outputs.ic_ft_mix)
    # rfft shape for 60 is 31, dropping DC (index 0) makes it 30
    assert ic_ft_mix.shape == (30, K)

    # File names are a result contract: only the trait/attribute names
    # changed, not the files written to disk.
    assert os.path.basename(result.outputs.ic_mix) == "ica_mix"
    assert os.path.basename(result.outputs.ic_ft_mix) == "ica_FTmix"


def test_residual_file_is_masked_float32_4d(tmp_path):
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path)

    result = _run(preproc_file, mask_file, components_file)

    res_img = nib.load(result.outputs.residual_file)
    assert res_img.shape == (5, 5, 5, T)
    assert res_img.get_data_dtype() == np.dtype(np.float32)

    mask = nib.load(mask_file).get_fdata() > 0
    res_data = res_img.get_fdata()
    assert np.all(res_data[~mask] == 0)


def test_stage1_regressors_are_spatially_centred_maps(tmp_path):
    # A large constant offset added to every component map must not change
    # the result: dual regression demeans the spatial maps before stage 1.
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, seed=1)

    z_baseline = _zstat(_run(preproc_file, mask_file, components_file))

    mask = nib.load(mask_file).get_fdata() > 0
    comps_img = nib.load(components_file)
    comps = comps_img.get_fdata()
    comps[mask] += 1000.0
    offset_components_file = tmp_path / "components_offset.nii.gz"
    nib.save(nib.Nifti1Image(comps, comps_img.affine), offset_components_file)

    z_offset = _zstat(_run(preproc_file, mask_file, str(offset_components_file)))

    np.testing.assert_allclose(z_offset, z_baseline, atol=1e-6)


def test_dof_scales_raw_t_by_expected_sqrt_factor(tmp_path):
    T = 60
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, T=T, seed=2)
    raw = dict(t_to_z=False)

    t_full = _zstat(_run(preproc_file, mask_file, components_file, **raw))
    reduced_dof = T - 20
    t_capped = _zstat(
        _run(preproc_file, mask_file, components_file, dof=reduced_dof, **raw)
    )

    expected_factor = np.sqrt((reduced_dof - (K + 1)) / (T - (K + 1)))
    mask = nib.load(mask_file).get_fdata() > 0
    ratio = t_capped[mask] / t_full[mask]
    np.testing.assert_allclose(ratio, expected_factor, atol=1e-6)


def test_z_is_t_to_z_of_raw_t_with_residual_dof(tmp_path):
    T = 60
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, T=T, seed=2)
    dof = T - 20

    t_raw = _zstat(
        _run(preproc_file, mask_file, components_file, dof=dof, t_to_z=False)
    )
    z = _zstat(_run(preproc_file, mask_file, components_file, dof=dof))

    mask = nib.load(mask_file).get_fdata() > 0
    eff = dof - (K + 1)
    np.testing.assert_allclose(z[mask], t_to_z(t_raw[mask], eff), atol=1e-10)
    # With few residual dof the Gaussian quantile is smaller than |t|.
    big = np.abs(t_raw[mask]) > 1
    assert np.all(np.abs(z[mask][big]) < np.abs(t_raw[mask][big]))


def test_uncentred_raw_t_reproduces_the_pre_port_algebra(tmp_path):
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, seed=4)
    mask = nib.load(mask_file).get_fdata() > 0

    # Offset maps make the centring difference visible.
    comps_img = nib.load(components_file)
    comps = comps_img.get_fdata()
    comps[mask] += 3.0
    offset_file = tmp_path / "components_offset.nii.gz"
    nib.save(nib.Nifti1Image(comps, comps_img.affine), offset_file)

    result = _run(
        preproc_file, mask_file, str(offset_file), centre_maps=False, t_to_z=False
    )
    z_port = _zstat(result)[mask]

    # Pre-port formula: uncentred maps as stage-1 regressors, raw t with
    # residual dof T - (K + 1).
    Y = nib.load(preproc_file).get_fdata()[mask]
    maps = comps[mask]
    Yt = Y.T - Y.T.mean(axis=0, keepdims=True)
    Tc = Yt @ np.linalg.pinv(maps.T)
    X = np.hstack([Tc, np.ones((T, 1))])
    beta = np.linalg.pinv(X) @ Yt
    res = Yt - X @ beta
    var_res = np.sum(res**2, axis=0) / max(T - (K + 1), 1)
    inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.outer(np.diag(inv)[:-1], var_res))
    se[se == 0] = 1e-10
    expected = (beta[:-1, :] / se).T

    np.testing.assert_allclose(z_port, expected, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(np.loadtxt(result.outputs.ic_mix), Tc, atol=1e-6)

    centred = _zstat(_run(preproc_file, mask_file, str(offset_file), t_to_z=False))
    assert not np.allclose(centred[mask], expected, atol=1e-3)


def test_t_to_z_matches_scipy_quantile_mapping():
    dof = 30
    t = np.linspace(-8, 8, 161)
    expected = stats.norm.isf(stats.t.sf(t, dof))
    np.testing.assert_allclose(t_to_z(t, dof), expected, atol=1e-8)


def test_t_to_z_is_odd_symmetric():
    t = np.array([0.0, 0.3, 1.0, 2.5, 7.0, 25.0, 60.0])
    np.testing.assert_allclose(t_to_z(-t, 30), -t_to_z(t, 30), atol=0)
    assert t_to_z(np.array([0.0]), 30)[0] == 0


def test_t_to_z_finite_and_monotone_in_the_far_tail():
    t = np.linspace(-60, 60, 2401)
    z = t_to_z(t, 30)
    assert np.all(np.isfinite(z))
    assert np.all(np.diff(z) > 0)
    # Far beyond the range where the survival function is a normal double.
    huge = t_to_z(np.array([1e9, 1e10, 1e20, 1e40, 1e80, 1e300]), 30)
    assert np.all(np.isfinite(huge))
    assert np.all(np.diff(huge) > 0)


@pytest.mark.parametrize("dof", [1, 2])
def test_t_to_z_exact_against_closed_forms(dof):
    # Closed-form survival functions: dof 1 (Cauchy) sf = atan(1/t)/pi;
    # dof 2 sf = 1 / (sqrt(2+t^2) (sqrt(2+t^2) + t)).
    t = np.logspace(-2, 150, 2000)
    if dof == 1:
        logp = np.log(np.arctan(1 / t) / np.pi)
    else:
        r = np.sqrt(2 + t * t)
        logp = -np.log(r) - np.log(r + t)
    np.testing.assert_allclose(t_to_z(t, dof), -special.ndtri_exp(logp), rtol=1e-12)


@pytest.mark.parametrize("dof", [30, 1000, 20000])
def test_incomplete_beta_series_matches_scipy_where_scipy_is_accurate(dof):
    t = np.logspace(0, 6, 20000)
    ref = stats.t.logsf(t, dof)
    band = (ref < -300) & (ref > -700)
    assert band.sum() > 100
    np.testing.assert_allclose(_t_logsf_series(t[band], dof), ref[band], rtol=1e-12)


def test_t_to_z_continuous_where_scipy_underflows_at_large_dof():
    # At dof 1000 scipy's log survival function underflows near t = 58;
    # z must stay smooth across that point (no jump from an approximation).
    t = np.arange(50.0, 70.0, 0.01)
    z = t_to_z(t, 1000)
    assert np.all(np.isfinite(z))
    step = np.diff(z)
    assert np.all(step > 0)
    assert step.max() < 1.5 * step.min()


def test_residual_file_orthogonal_to_stage1_time_courses(tmp_path):
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, seed=3)

    result = _run(preproc_file, mask_file, components_file)

    mask = nib.load(mask_file).get_fdata() > 0
    res = nib.load(result.outputs.residual_file).get_fdata()[mask]  # (V, T)
    ic_mix = np.loadtxt(result.outputs.ic_mix)  # (T, K)

    res_c = res - res.mean(axis=1, keepdims=True)
    tc_c = ic_mix - ic_mix.mean(axis=0, keepdims=True)
    res_std = res_c.std(axis=1, keepdims=True)
    res_std[res_std == 0] = 1
    tc_std = tc_c.std(axis=0, keepdims=True)
    tc_std[tc_std == 0] = 1
    corr = (res_c / res_std) @ (tc_c / tc_std) / T  # (V, K)

    assert np.max(np.abs(corr)) < 1e-6


@pytest.mark.parametrize("dof", [3, 0, -5])
def test_no_residual_dof_raises_a_clear_error(tmp_path, dof):
    """dof - (K + 1) < 1 leaves no residual degrees of freedom for the
    stage-2 t statistics: the node stops with an explanation instead of
    writing maps from a floored dof."""
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, K=2)
    with pytest.raises(ValueError, match="residual degrees of freedom"):
        _run(preproc_file, mask_file, components_file, dof=dof)


def test_one_residual_dof_still_runs(tmp_path):
    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path, K=2)
    result = _run(preproc_file, mask_file, components_file, dof=K + 2)
    assert np.all(np.isfinite(_zstat(result)))


def test_residual_file_not_written_when_disabled(tmp_path):
    from nipype.interfaces.base import isdefined

    preproc_file, mask_file, components_file, T, K = _make_inputs(tmp_path)
    result = _run(preproc_file, mask_file, components_file, write_residuals=False)
    assert not isdefined(result.outputs.residual_file)
    assert not (tmp_path / "dr_residuals.nii.gz").exists()
    assert os.path.exists(result.outputs.zstat_file)
