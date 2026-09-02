"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DwiBiasCorrection.DwiBiasCorrection`.

The node's scientific contract is the point of the whole task: the N4 bias
field is estimated **once**, on the mean b0, and that single field is applied
to every DWI volume. Re-estimating the field per volume, or correcting only the
b0, is a silent scientific error. These tests spy on the antspyx N4 estimator to
prove it is invoked exactly once, on the mean-b0 image, and that the correction
applied to volume *k* is that same field.
"""

import os

import numpy as np
import nibabel as nib

from swane.nipype_pipeline.nodes.DwiBiasCorrection import (
    DwiBiasCorrection,
    OMP_THREADS_VAR,
    OPENBLAS_THREADS_VAR,
    ITK_THREADS_VAR,
    B0_MAX_BVAL,
)


def _make_bval(tmp_path, bvals):
    bval_path = tmp_path / "dwi.bval"
    np.savetxt(bval_path, np.asarray(bvals)[np.newaxis, :], fmt="%d")
    return str(bval_path)


def _install_n4_spy(monkeypatch, field, calls):
    """Replace ``ants.n4_bias_field_correction`` with a spy returning ``field``.

    Records every call's input image (as a numpy array) and the thread-env
    values seen at call time, so a test can assert the estimator ran exactly
    once, on the expected image, with the threads pinned.
    """
    import ants

    def _spy(image, **kwargs):
        calls.setdefault("count", 0)
        calls["count"] += 1
        calls["image"] = image.numpy()
        calls["return_bias_field"] = kwargs.get("return_bias_field")
        calls["omp"] = os.environ.get(OMP_THREADS_VAR)
        calls["openblas"] = os.environ.get(OPENBLAS_THREADS_VAR)
        calls["itk"] = os.environ.get(ITK_THREADS_VAR)
        return ants.from_numpy(field.astype(np.float32))

    monkeypatch.setattr(ants, "n4_bias_field_correction", _spy)


class TestDwiBiasCorrectionScientificContract:
    def test_field_estimated_once_on_mean_b0_and_applied_to_all_volumes(
        self, workspace, make_nifti, monkeypatch
    ):
        rng = np.random.default_rng(0)
        shape = (5, 6, 7)
        # Two b0 volumes and three diffusion-weighted ones; the b0s differ so
        # the mean b0 is a genuine average, not a copy of a single volume.
        b0a = rng.random(shape).astype(np.float32) + 1.0
        b0b = rng.random(shape).astype(np.float32) + 1.0
        dw1 = rng.random(shape).astype(np.float32) + 1.0
        dw2 = rng.random(shape).astype(np.float32) + 1.0
        dw3 = rng.random(shape).astype(np.float32) + 1.0
        data = np.stack([b0a, dw1, b0b, dw2, dw3], axis=-1)
        bvals = [0, 1000, 0, 1000, 1000]

        affine = np.diag([2.0, 2.0, 2.5, 1.0])
        in_file = make_nifti("dwi.nii.gz", data=data, affine=affine)
        bval = _make_bval(workspace, bvals)

        # A known, strictly-positive multiplicative field.
        field = rng.random(shape).astype(np.float32) + 0.5

        calls = {}
        _install_n4_spy(monkeypatch, field, calls)

        node = DwiBiasCorrection()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.run()

        # The estimator ran exactly once (not once per volume) ...
        assert calls["count"] == 1
        # ... asking antspyx for the bias field itself ...
        assert calls["return_bias_field"] is True
        # ... on the mean of the two b0 volumes.
        expected_mean_b0 = np.mean([b0a, b0b], axis=0)
        assert np.allclose(calls["image"], expected_mean_b0, atol=1e-5)

        outputs = node._list_outputs()
        out_img = nib.load(outputs["out_file"])
        out_data = out_img.get_fdata(dtype=np.float32)

        # Same volume count and geometry as the input.
        assert out_data.shape == data.shape
        assert np.allclose(out_img.affine, affine)

        # Every volume was divided by that single field.
        expected = data / field[..., np.newaxis]
        assert np.allclose(out_data, expected, atol=1e-4)

        # The published bias field is the estimated one, at DWI spatial shape.
        field_img = nib.load(outputs["bias_field"])
        assert field_img.shape == shape
        assert np.allclose(field_img.get_fdata(dtype=np.float32), field, atol=1e-5)

    def test_b0_located_by_bval_threshold(self, workspace, make_nifti, monkeypatch):
        rng = np.random.default_rng(1)
        shape = (4, 4, 4)
        vols = [rng.random(shape).astype(np.float32) + 1.0 for _ in range(4)]
        data = np.stack(vols, axis=-1)
        # Only the last volume is a true b0; a low but non-zero bval below the
        # threshold must still count as a b0.
        bvals = [1000, 1000, int(B0_MAX_BVAL) - 1, 1000]

        in_file = make_nifti("dwi.nii.gz", data=data)
        bval = _make_bval(workspace, bvals)
        field = np.ones(shape, dtype=np.float32)

        calls = {}
        _install_n4_spy(monkeypatch, field, calls)

        node = DwiBiasCorrection()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.run()

        assert calls["count"] == 1
        assert np.allclose(calls["image"], vols[2], atol=1e-5)


class TestDwiBiasCorrectionThreadPinning:
    def test_omp_openblas_itk_pinned_during_run_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        monkeypatch.delenv(OPENBLAS_THREADS_VAR, raising=False)
        monkeypatch.delenv(ITK_THREADS_VAR, raising=False)

        shape = (4, 4, 4)
        data = np.stack(
            [np.ones(shape, dtype=np.float32), np.ones(shape, dtype=np.float32)],
            axis=-1,
        )
        in_file = make_nifti("dwi.nii.gz", data=data)
        bval = _make_bval(workspace, [0, 1000])
        field = np.ones(shape, dtype=np.float32)

        calls = {}
        _install_n4_spy(monkeypatch, field, calls)

        node = DwiBiasCorrection()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.num_threads = 3
        node.run()

        assert calls["omp"] == "3"
        assert calls["openblas"] == "3"
        assert calls["itk"] == "3"
        assert OMP_THREADS_VAR not in os.environ
        assert OPENBLAS_THREADS_VAR not in os.environ
        assert ITK_THREADS_VAR not in os.environ


class TestDwiBiasCorrectionRealN4:
    """A real (un-mocked) N4 run, to prove the wiring holds end to end."""

    def test_real_run_preserves_geometry_and_volume_count(self, workspace, make_nifti):
        rng = np.random.default_rng(2)
        shape = (8, 8, 8)
        data = np.stack(
            [rng.random(shape).astype(np.float32) + 1.0 for _ in range(3)],
            axis=-1,
        )
        affine = np.diag([1.5, 1.5, 2.0, 1.0])
        in_file = make_nifti("dwi.nii.gz", data=data, affine=affine)
        bval = _make_bval(workspace, [0, 1000, 1000])

        node = DwiBiasCorrection()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.run()

        outputs = node._list_outputs()
        out_img = nib.load(outputs["out_file"])
        assert out_img.shape == data.shape
        assert np.allclose(out_img.affine, affine)
        assert np.all(np.isfinite(out_img.get_fdata(dtype=np.float32)))

        field_img = nib.load(outputs["bias_field"])
        assert field_img.shape == shape
        assert np.all(np.isfinite(field_img.get_fdata(dtype=np.float32)))
