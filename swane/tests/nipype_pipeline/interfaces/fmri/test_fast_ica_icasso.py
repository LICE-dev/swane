import json
import logging
import os

import numpy as np
import nibabel as nib
import pytest
from scipy.optimize import linear_sum_assignment

from swane.nipype_pipeline.interfaces.fmri.FastIcaIcasso import FastIcaIcasso


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path, monkeypatch):
    # The interface writes its outputs to the current directory.
    monkeypatch.chdir(tmp_path)


def _mixed_sources(
    tmp_path, T=150, K=4, shape=(20, 10, 10), p_active=0.15, noise_sd=0.3, seed=0
):
    """Independent super-Gaussian spatial maps (sparse +-1, most voxels 0 --
    high positive kurtosis) mixed by random unit-variance time courses, plus
    a homoskedastic noise floor, then reshaped to a 4D volume.

    The interface variance-normalises each voxel's time course before
    FastICA; a per-voxel-varying source amplitude (e.g. plain Laplace
    maps) would make that per-voxel rescaling nonlinear in the true sources
    and destroy the ground-truth correlation used below, so the sparse
    fixed-amplitude design keeps voxel variance roughly homogeneous instead.
    """
    rng = np.random.default_rng(seed)
    V = int(np.prod(shape))
    active = rng.random((V, K)) < p_active
    sign = rng.choice([-1.0, 1.0], size=(V, K))
    S_true = active * sign
    A_true = rng.standard_normal((T, K))
    A_true = (A_true - A_true.mean(0)) / A_true.std(0)
    X_vt = S_true @ A_true.T + rng.standard_normal((V, T)) * noise_sd

    data = X_vt.reshape(shape + (T,)).astype(np.float32)
    mask = np.ones(shape, dtype=np.uint8)

    in_file = tmp_path / "twin.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), in_file)
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    return str(in_file), str(mask_file), S_true, K


def _best_match_abs_r(maps_vk, true_vk):
    Mz = (maps_vk - maps_vk.mean(0)) / (maps_vk.std(0) + 1e-12)
    Tz = (true_vk - true_vk.mean(0)) / (true_vk.std(0) + 1e-12)
    r = (Tz.T @ Mz) / Mz.shape[0]
    rows, cols = linear_sum_assignment(-np.abs(r))
    return np.abs(r[rows, cols])


def test_recovers_super_gaussian_sources(tmp_path):
    in_file, mask_file, S_true, K = _mixed_sources(tmp_path)

    interface = FastIcaIcasso()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_components = K
    interface.inputs.n_runs = 3

    result = interface.run()

    mask = nib.load(mask_file).get_fdata() > 0
    maps = nib.load(result.outputs.components_file).get_fdata()[mask]

    matched_r = _best_match_abs_r(maps, S_true)
    assert np.all(matched_r > 0.95)


def test_deterministic_for_same_random_state(tmp_path):
    in_file, mask_file, S_true, K = _mixed_sources(tmp_path, seed=1)

    first = FastIcaIcasso()
    first.inputs.in_file = in_file
    first.inputs.mask_file = mask_file
    first.inputs.n_components = K
    first.inputs.n_runs = 2
    first.inputs.random_state = 7
    maps_1 = nib.load(first.run().outputs.components_file).get_fdata()

    second = FastIcaIcasso()
    second.inputs.in_file = in_file
    second.inputs.mask_file = mask_file
    second.inputs.n_components = K
    second.inputs.n_runs = 2
    second.inputs.random_state = 7
    maps_2 = nib.load(second.run().outputs.components_file).get_fdata()

    assert np.max(np.abs(maps_1 - maps_2)) == 0


def test_max_iter_cap_warns_and_still_writes_output(tmp_path, caplog):
    in_file, mask_file, S_true, K = _mixed_sources(tmp_path, seed=2)

    interface = FastIcaIcasso()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_components = K
    interface.inputs.n_runs = 2
    interface.inputs.max_iter = 2

    with caplog.at_level(logging.WARNING, logger="nipype.interface"):
        result = interface.run()

    assert "maximum number of iterations" in caplog.text
    assert os.path.exists(result.outputs.components_file)


def test_report_lists_one_entry_per_run(tmp_path):
    in_file, mask_file, S_true, K = _mixed_sources(tmp_path, seed=3)

    n_runs = 4
    interface = FastIcaIcasso()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_components = K
    interface.inputs.n_runs = n_runs

    result = interface.run()

    with open(result.outputs.report_file) as fh:
        report = json.load(fh)

    assert len(report["n_iter"]) == n_runs
    assert len(report["converged"]) == n_runs
    assert len(report["cross_isi_scores"]) == n_runs
    assert "selected_run" in report
    assert "iq_per_cluster" in report


def test_icasso_clusters_tolerates_round_off_above_one():
    """|r| between identical maps can exceed 1 by round-off (always the case
    with a single component, where every run finds the same map); the
    distance 1 - |r| must not become a negative linkage distance."""
    from swane.nipype_pipeline.interfaces.fmri.FastIcaIcasso import _icasso_clusters

    R = np.full((10, 10), 1.0 + 4e-16)
    cl = _icasso_clusters(R, 1)
    assert list(cl) == [0] * 10

    R2 = np.array(
        [
            [1.0, 1.0 + 2e-16, 0.1, 0.1],
            [1.0 + 2e-16, 1.0, 0.1, 0.1],
            [0.1, 0.1, 1.0, 0.9],
            [0.1, 0.1, 0.9, 1.0],
        ]
    )
    cl2 = _icasso_clusters(R2, 2)
    assert cl2[0] == cl2[1] and cl2[2] == cl2[3] and cl2[0] != cl2[2]


def _strict_json(path):
    """Load JSON rejecting the non-standard NaN/Infinity constants."""

    def _reject(name):
        raise ValueError("non-standard JSON constant %s" % name)

    with open(path) as fh:
        return json.loads(fh.read(), parse_constant=_reject)


def test_n_components_above_data_rank_is_clamped(tmp_path, caplog):
    """Requesting more components than the data rank (T timepoints, minus the
    temporal mean removed by the variance normalisation) must not crash: the
    number is clamped and the node log states both values."""
    T = 12
    in_file, mask_file, _, _ = _mixed_sources(tmp_path, T=T, K=2, seed=4)

    interface = FastIcaIcasso()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_components = 20
    interface.inputs.n_runs = 2
    interface.inputs.max_iter = 200

    with caplog.at_level(logging.WARNING, logger="nipype.interface"):
        result = interface.run()

    report = _strict_json(result.outputs.report_file)
    used = report["n_components"]
    assert report["n_components_requested"] == 20
    assert used == T - 1
    assert nib.load(result.outputs.components_file).shape[-1] == used
    assert "20" in caplog.text and str(used) in caplog.text


@pytest.mark.parametrize("K, n_runs", [(1, 3), (3, 1), (1, 1)])
def test_single_component_or_run_gives_finite_report(tmp_path, K, n_runs):
    """With K = 1 the Amari index has no off-diagonal terms and with a single
    run there is no other run to compare: the cross-ISI scores must be finite
    (standard JSON) and no RuntimeWarning raised."""
    import warnings

    in_file, mask_file, _, _ = _mixed_sources(tmp_path, K=max(K, 1), seed=5)

    interface = FastIcaIcasso()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_components = K
    interface.inputs.n_runs = n_runs

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = interface.run()

    report = _strict_json(result.outputs.report_file)
    assert len(report["cross_isi_scores"]) == n_runs
    assert all(np.isfinite(report["cross_isi_scores"]))
