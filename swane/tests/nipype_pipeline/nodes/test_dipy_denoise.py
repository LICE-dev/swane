"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyDenoise.DipyDenoise`.

The node always denoises with dipy's ``nlmeans`` filter, using a noise level
estimated with ``estimate_sigma`` beforehand (no MP-PCA choice; see the dipy
+ RecoBundles design, section 2). The tests below run the real dipy filter on
tiny synthetic data -- fast enough at this size -- and spy on
``estimate_sigma``/``nlmeans`` only to check *what* they were called with, not
to fake the computation.
"""

import os

import numpy as np
import nibabel as nib

from swane.nipype_pipeline.nodes.DipyDenoise import (
    DipyDenoise,
    OMP_THREADS_VAR,
    OPENBLAS_THREADS_VAR,
)


def _make_bval_bvec(tmp_path, n):
    bval_path = tmp_path / "dwi.bval"
    bvec_path = tmp_path / "dwi.bvec"
    np.savetxt(bval_path, np.zeros((1, n)), fmt="%d")
    np.savetxt(bvec_path, np.zeros((3, n)), fmt="%.6f")
    return str(bval_path), str(bvec_path)


class TestDipyDenoiseContract:
    def test_estimate_sigma_called_on_data_passed_to_nlmeans(
        self, workspace, make_nifti, monkeypatch
    ):
        import dipy.denoise.nlmeans as nlmeans_module
        import dipy.denoise.noise_estimate as noise_estimate_module

        data = np.random.rand(4, 4, 4, 5).astype(np.float32)
        in_file = make_nifti("dwi.nii.gz", data=data)
        bval, bvec = _make_bval_bvec(workspace, n=5)

        calls = {}
        real_estimate_sigma = noise_estimate_module.estimate_sigma

        def _spy_estimate_sigma(arr, **kwargs):
            calls["estimate_sigma_arr"] = arr
            sigma = real_estimate_sigma(arr, **kwargs)
            calls["sigma"] = sigma
            return sigma

        def _spy_nlmeans(arr, sigma, **kwargs):
            calls["nlmeans_arr"] = arr
            calls["nlmeans_sigma"] = sigma
            return arr

        monkeypatch.setattr(
            noise_estimate_module, "estimate_sigma", _spy_estimate_sigma
        )
        monkeypatch.setattr(nlmeans_module, "nlmeans", _spy_nlmeans)

        node = DipyDenoise()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.run()

        assert np.array_equal(calls["estimate_sigma_arr"], data)
        assert np.array_equal(calls["nlmeans_arr"], data)
        assert np.array_equal(calls["nlmeans_sigma"], calls["sigma"])


class TestDipyDenoisePreservesGeometry:
    def test_output_preserves_shape_affine_and_volume_count(
        self, workspace, make_nifti
    ):
        rng = np.random.default_rng(0)
        shape = (6, 6, 6, 4)
        data = (rng.random(shape) * 100).astype(np.float32)
        affine = np.diag([2.0, 2.0, 2.0, 1.0])
        in_file = make_nifti("dwi.nii.gz", data=data, affine=affine)
        bval, bvec = _make_bval_bvec(workspace, n=4)

        node = DipyDenoise()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.run()

        out_path = node._list_outputs()["out_file"]
        out_img = nib.load(out_path)
        assert out_img.shape == shape
        assert np.allclose(out_img.affine, affine)


class TestDipyDenoiseThreadPinning:
    def test_omp_and_openblas_threads_pinned_during_run_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        import dipy.denoise.nlmeans as nlmeans_module

        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)
        monkeypatch.delenv(OPENBLAS_THREADS_VAR, raising=False)

        data = np.random.rand(4, 4, 4, 4).astype(np.float32)
        in_file = make_nifti("dwi.nii.gz", data=data)
        bval, bvec = _make_bval_bvec(workspace, n=4)

        seen = {}

        def _spy(arr, sigma, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            seen["openblas"] = os.environ.get(OPENBLAS_THREADS_VAR)
            return arr

        monkeypatch.setattr(nlmeans_module, "nlmeans", _spy)

        node = DipyDenoise()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.num_threads = 3
        node.run()

        assert seen["omp"] == str(3)
        assert seen["openblas"] == str(3)
        assert OMP_THREADS_VAR not in os.environ
        assert OPENBLAS_THREADS_VAR not in os.environ
