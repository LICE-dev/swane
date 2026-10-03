import os
import numpy as np
import nibabel as nib
from swane.nipype_pipeline.interfaces.fmri.NilearnAutoDim import NilearnAutoDim


def test_nilearn_auto_dim(tmp_path):
    in_file = tmp_path / "mc.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"

    # Create synthetic 4D data (4x4x4x50)
    data = np.random.RandomState(0).randn(4, 4, 4, 50)
    # add some structure
    data[1:3, 1:3, 1:3, :] += np.sin(np.linspace(0, 10, 50))
    nib.save(nib.Nifti1Image(data, np.eye(4)), in_file)

    mask = np.zeros((4, 4, 4))
    mask[1:3, 1:3, 1:3] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_file)

    interface = NilearnAutoDim()
    interface.inputs.in_file = str(in_file)
    interface.inputs.mask_file = str(mask_file)

    result = interface.run()

    assert result.outputs.n_components >= 1
    assert isinstance(result.outputs.n_components, int)


def _regressed_sources(tmp_path, T=120, K=6, p=8, seed=0, floor_mult=5.0):
    """A synthetic 4D series whose temporal covariance has K genuine signal
    eigenvalues, T-n_removed-K genuine background-noise eigenvalues, and
    n_removed "removed" eigenvalues pinned to a tiny floor -- just above the
    float64 numerical-rank tolerance used by estimate_dim_mdl, but many
    orders of magnitude below the signal.

    This reproduces (rather than an exact-zero regression residual, whose
    round-off stays far below the tolerance) the actual failure mode: a
    regression already applied upstream (e.g. NuisanceRegression) writes
    its residual through a float32 NIfTI round trip, and that quantization
    noise lands on the "removed" directions at a magnitude that clears the
    numerical-rank tolerance. Without the cap, every one of those directions
    counts as a real eigenvalue, so the MDL tail ratio never favours a low
    rank; capped by n_removed, the true K is recovered (see the module
    docstring for the mechanism, and REPORT_POST_AROMA.md for the derivation
    of n_removed = rank(X including the constant) + n_AROMA).

    Numbers checked while writing this fixture (seed=0, T=120, K=6, p=8,
    16x16x12 mask): the exact-projection residual (lstsq at float64 or
    float32 precision, then optionally cast to float32) leaves the 9 removed
    eigenvalues at ~1e-14, far below tol (~1e-11), and does NOT reproduce the
    explosion (uncapped estimate stays ~5). Pinning those eigenvalues to a
    floor of 1x-30x tol reliably reproduces it (uncapped estimate jumps to
    ~110; capped recovers K within +/-1).
    """
    rng = np.random.default_rng(seed)
    shape = (16, 16, 12)
    mask = np.ones(shape, bool)
    n_voxels = int(mask.sum())
    n_removed = p + 1

    signal_ev = np.sort(rng.uniform(8, 14, K))[::-1]
    noise_ev = np.sort(rng.uniform(0.2, 1.0, T - n_removed - K))[::-1]
    tol_scale = signal_ev.max() * n_voxels
    floor = floor_mult * tol_scale * np.finfo(np.float64).eps
    removed_ev = np.full(n_removed, floor)
    ev_full = np.concatenate([signal_ev, noise_ev, removed_ev])

    basis, _ = np.linalg.qr(rng.standard_normal((T, T)))
    loading = basis * np.sqrt(np.clip(ev_full, 0, None))
    Y = (rng.standard_normal((n_voxels, T)) @ loading.T).astype(np.float32)

    data = np.zeros(shape + (T,), np.float32)
    data[mask] = Y
    f = tmp_path / "reg.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), f)
    m = tmp_path / "mask.nii.gz"
    nib.save(nib.Nifti1Image(mask.astype(np.uint8), np.eye(4)), m)
    return str(f), str(m), n_removed


def test_rank_cap_reproduces_explosion_without_n_removed(tmp_path):
    in_file, mask_file, n_removed = _regressed_sources(tmp_path, K=6)
    interface = NilearnAutoDim()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_removed = 0

    result = interface.run()

    assert result.outputs.n_components >= 3 * 6


def test_rank_cap_recovers_true_k_with_n_removed(tmp_path):
    in_file, mask_file, n_removed = _regressed_sources(tmp_path, K=6)
    interface = NilearnAutoDim()
    interface.inputs.in_file = in_file
    interface.inputs.mask_file = mask_file
    interface.inputs.n_removed = n_removed

    result = interface.run()

    assert abs(result.outputs.n_components - 6) <= 2


def test_n_removed_at_or_above_t_warns_and_returns_one(tmp_path, caplog):
    """A regression that removed as many directions as there are volumes
    leaves no rank for the estimate: one component, with a node warning,
    instead of a negative-size array error."""
    import logging

    in_file = tmp_path / "short.nii.gz"
    mask_file = tmp_path / "mask.nii.gz"
    T = 20
    data = np.random.RandomState(1).randn(4, 4, 4, T)
    nib.save(nib.Nifti1Image(data, np.eye(4)), in_file)
    nib.save(nib.Nifti1Image(np.ones((4, 4, 4)), np.eye(4)), mask_file)

    interface = NilearnAutoDim()
    interface.inputs.in_file = str(in_file)
    interface.inputs.mask_file = str(mask_file)
    interface.inputs.n_removed = 28

    with caplog.at_level(logging.WARNING, logger="nipype.interface"):
        result = interface.run()

    assert result.outputs.n_components == 1
    assert "28" in caplog.text and str(T) in caplog.text
