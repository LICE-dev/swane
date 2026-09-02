"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyCsdFit.DipyCsdFit`.

The load-bearing behaviour here is the adaptive ``sh_order_max``: fitting more
spherical-harmonic coefficients than the angular sampling supports silently
over-fits sparse data. The direction -> lmax mapping is therefore tested
directly against the spec table, at every boundary, through a pure helper.

The direction count that drives it is the number of *non-b0* gradient
directions (``~gtab.b0s_mask``), never the total volume count -- that
definition is asserted here so the node and the test agree on it.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.DipyCsdFit import (
    DipyCsdFit,
    sh_order_for_directions,
    n_directions_from_gtab,
    OMP_THREADS_VAR,
    OPENBLAS_THREADS_VAR,
)


def _coeff_count(sh_order):
    """Number of SH coefficients for an even order ``sh_order``."""
    return (sh_order + 1) * (sh_order + 2) // 2


def _gtab(n_directions, n_b0=1, seed=42):
    """A single-shell gradient table: ``n_b0`` b0s plus ``n_directions``
    unit directions. Total volume count deliberately differs from the
    direction count so tests can tell the two apart."""
    from dipy.core.gradients import gradient_table

    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(n_directions, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    bvals = np.concatenate([np.zeros(n_b0), np.full(n_directions, 1000.0)])
    bvecs = np.vstack([np.zeros((n_b0, 3)), dirs])
    return gradient_table(bvals, bvecs=bvecs), bvals, bvecs


def _gtab_files(tmp_path, bvals, bvecs, name="dwi"):
    bval_path = tmp_path / f"{name}.bval"
    bvec_path = tmp_path / f"{name}.bvec"
    np.savetxt(bval_path, bvals[None, :], fmt="%g")
    np.savetxt(bvec_path, bvecs.T, fmt="%.6f")
    return str(bval_path), str(bvec_path)


class TestShOrderForDirections:
    """The spec section 5 direction -> lmax table, boundary by boundary."""

    @pytest.mark.parametrize(
        "n_dirs, expected_lmax",
        [
            # the exact boundaries called out in the plan
            (45, 8),
            (44, 6),
            (28, 6),
            (27, 4),
            (15, 4),
            (14, 2),
            (6, 2),
            # interior points
            (100, 8),
            (30, 6),
            (20, 4),
            (10, 2),
        ],
    )
    def test_boundaries(self, n_dirs, expected_lmax):
        assert sh_order_for_directions(n_dirs) == expected_lmax

    @pytest.mark.parametrize("n_dirs", [5, 1, 0])
    def test_below_floor_clamps_to_two(self, n_dirs):
        # SWANe supports >= 15 directions; anything under the lowest table
        # tier still returns the lmax=2 floor rather than raising.
        assert sh_order_for_directions(n_dirs) == 2


class TestNDirectionsFromGtab:
    """The direction count comes from the non-b0 mask, not the volume count."""

    def test_counts_non_b0_volumes_only(self):
        gtab, _, _ = _gtab(n_directions=30, n_b0=3)
        # total volumes = 33, but only 30 are gradient directions
        assert n_directions_from_gtab(gtab) == int(np.count_nonzero(~gtab.b0s_mask))
        assert n_directions_from_gtab(gtab) == 30

    def test_multiple_b0s_do_not_inflate_lmax(self):
        # 30 directions -> lmax 6, regardless of how many b0s pad the series
        gtab, _, _ = _gtab(n_directions=30, n_b0=5)
        assert sh_order_for_directions(n_directions_from_gtab(gtab)) == 6


class TestDipyCsdFitContract:
    """The real dipy path on a tiny synthetic single-tensor volume."""

    def test_shm_coeff_shape_follows_non_b0_direction_count(
        self, workspace, make_nifti
    ):
        from dipy.sims.voxel import single_tensor

        n_dirs, n_b0 = 30, 2  # 32 volumes, 30 directions -> lmax 6
        gtab, bvals, bvecs = _gtab(n_directions=n_dirs, n_b0=n_b0)
        bval, bvec = _gtab_files(workspace, bvals, bvecs)

        sig = single_tensor(gtab, S0=100.0, evals=np.array([0.0015, 0.0003, 0.0003]))
        shape = (4, 4, 4)
        data = np.tile(sig, shape + (1,)).astype(np.float32)
        in_file = make_nifti("dwi.nii.gz", data=data)
        mask_file = make_nifti("mask.nii.gz", data=np.ones(shape, dtype=np.float32))

        node = DipyCsdFit()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.mask = mask_file
        node.run()

        out_path = node._list_outputs()["shm_coeff"]
        shm = nib.load(out_path).get_fdata()

        assert shm.shape == shape + (_coeff_count(6),)  # 28 coeffs at lmax 6
        assert np.all(np.isfinite(shm))


class TestDipyCsdFitThreadPinning:
    """BLAS pinned to 1 per worker; parallelism comes from ``num_processes``."""

    def test_blas_pinned_to_one_and_num_processes_follows_num_threads(
        self, workspace, make_nifti, monkeypatch
    ):
        import dipy.direction as direction_module
        import dipy.reconst.csdeconv as csd_module

        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        monkeypatch.delenv(OPENBLAS_THREADS_VAR, raising=False)

        n_dirs, n_b0 = 30, 1
        gtab, bvals, bvecs = _gtab(n_directions=n_dirs, n_b0=n_b0)
        bval, bvec = _gtab_files(workspace, bvals, bvecs)
        shape = (4, 4, 4)
        data = np.ones(shape + (n_dirs + n_b0,), dtype=np.float32) * 100
        in_file = make_nifti("dwi.nii.gz", data=data)
        mask_file = make_nifti("mask.nii.gz", data=np.ones(shape, dtype=np.float32))

        # Avoid the real (heavy, subprocess-spawning) computation: record what
        # the node hands to dipy and hand back a correctly shaped result.
        seen = {}

        def _fake_response(gt, dt, **kwargs):
            return (np.array([0.0015, 0.0003, 0.0003]), 100.0), 0.2

        def _fake_peaks(model, dt, sphere, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            seen["openblas"] = os.environ.get(OPENBLAS_THREADS_VAR)
            seen["num_processes"] = kwargs.get("num_processes")
            seen["sh_order_max"] = kwargs.get("sh_order_max")

            class _PAM:
                pass

            pam = _PAM()
            n_coeff = _coeff_count(kwargs.get("sh_order_max"))
            pam.shm_coeff = np.zeros(dt.shape[:-1] + (n_coeff,), dtype=np.float32)
            return pam

        monkeypatch.setattr(csd_module, "auto_response_ssst", _fake_response)
        monkeypatch.setattr(direction_module, "peaks_from_model", _fake_peaks)

        node = DipyCsdFit()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.mask = mask_file
        node.inputs.num_threads = 4
        node.run()

        # BLAS pinned to a single thread per worker (parallelism is by process)
        assert seen["omp"] == "1"
        assert seen["openblas"] == "1"
        # the declared core count drives the process pool, and lmax is adaptive
        assert seen["num_processes"] == 4
        assert seen["sh_order_max"] == 6
        # env restored to its (absent) prior state
        assert OMP_THREADS_VAR not in os.environ
        assert OPENBLAS_THREADS_VAR not in os.environ
