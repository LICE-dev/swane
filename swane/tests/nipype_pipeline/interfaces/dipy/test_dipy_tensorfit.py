"""Unit tests for
:class:`swane.nipype_pipeline.interfaces.dipy.DipyTensorFit.DipyTensorFit`.

Runs dipy's real tensor model on tiny synthetic gradient data -- cheap enough
at this size -- and checks the FA map's shape and finiteness, plus the OMP
thread pin (this node is declared ``n_procs=1`` and must not let numpy/BLAS
silently use more).
"""

import os

import numpy as np
import nibabel as nib

from swane.nipype_pipeline.interfaces.dipy.DipyTensorFit import (
    DipyTensorFit,
    OMP_THREADS_VAR,
)


def _single_shell_gtab_files(tmp_path, n_directions=6):
    """A minimal single-shell gradient table: one b0 plus ``n_directions``
    roughly uniform unit directions, written as FSL-style bval/bvec files."""
    rng = np.random.default_rng(42)
    dirs = rng.normal(size=(n_directions, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)

    bvals = np.concatenate([[0], np.full(n_directions, 1000)])
    bvecs = np.vstack([[0, 0, 0], dirs])

    bval_path = tmp_path / "dwi.bval"
    bvec_path = tmp_path / "dwi.bvec"
    np.savetxt(bval_path, bvals[None, :], fmt="%d")
    np.savetxt(bvec_path, bvecs.T, fmt="%.6f")
    return str(bval_path), str(bvec_path), bvals, bvecs


class TestDipyTensorFitLoadsFloat32:
    """dipy's TensorModel upcasts to float64 internally, so loading the DWI as
    float32 (rather than get_fdata's float64 default) is FA-lossless (~1e-7)
    while halving the input buffer's RAM."""

    def test_data_passed_to_fit_is_float32(self, workspace, make_nifti, monkeypatch):
        from dipy.reconst import dti

        shape = (5, 5, 5)
        bval, bvec, bvals, _ = _single_shell_gtab_files(workspace)
        data = (np.random.default_rng(1).random(shape + (len(bvals),)) * 100).astype(
            np.float32
        )
        in_file = make_nifti("dwi.nii.gz", data=data)
        mask_file = make_nifti("mask.nii.gz", data=np.ones(shape, dtype=np.float32))

        seen = {}
        real_fit = dti.TensorModel.fit

        def _spy_fit(self, data_arg, **kwargs):
            seen["dtype"] = np.asarray(data_arg).dtype
            return real_fit(self, data_arg, **kwargs)

        monkeypatch.setattr(dti.TensorModel, "fit", _spy_fit)

        node = DipyTensorFit()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.mask = mask_file
        node.run()

        assert seen["dtype"] == np.dtype(np.float32)


class TestDipyTensorFitContract:
    def test_fa_has_correct_shape_and_is_finite(self, workspace, make_nifti):
        shape = (6, 6, 6)
        bval, bvec, bvals, bvecs = _single_shell_gtab_files(workspace)
        n_vols = len(bvals)

        rng = np.random.default_rng(0)
        data = (rng.random(shape + (n_vols,)) * 100 + 50).astype(np.float32)
        in_file = make_nifti("dwi.nii.gz", data=data)

        mask = np.zeros(shape, dtype=np.float32)
        mask[1:5, 1:5, 1:5] = 1.0
        mask_file = make_nifti("mask.nii.gz", data=mask)

        node = DipyTensorFit()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.mask = mask_file
        node.run()

        out_path = node._list_outputs()["fa"]
        fa = nib.load(out_path).get_fdata()

        assert fa.shape == shape
        assert np.all(np.isfinite(fa))
        assert np.all(fa >= 0.0) and np.all(fa <= 1.0 + 1e-6)


class TestDipyTensorFitThreadPinning:
    def test_omp_pinned_to_one_during_fit_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        import dipy.reconst.dti as dti_module

        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)

        shape = (4, 4, 4)
        bval, bvec, bvals, bvecs = _single_shell_gtab_files(workspace)
        n_vols = len(bvals)
        data = np.ones(shape + (n_vols,), dtype=np.float32) * 100
        in_file = make_nifti("dwi.nii.gz", data=data)
        mask_file = make_nifti("mask.nii.gz", data=np.ones(shape, dtype=np.float32))

        seen = {}
        real_init = dti_module.TensorModel.__init__

        def _spy_init(self, gtab, *args, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            return real_init(self, gtab, *args, **kwargs)

        monkeypatch.setattr(dti_module.TensorModel, "__init__", _spy_init)

        node = DipyTensorFit()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.mask = mask_file
        node.run()

        assert seen["omp"] == "1"
        assert OMP_THREADS_VAR not in os.environ


class TestDipyTensorFitOutputDtype:
    """FA is a float map: it must be written as float32 whatever the on-disk
    dtype of the DWI whose header it inherits. With an int16 DWI header the FA
    was written as scaled int16, quantised to ~1e-5 steps."""

    def _fit(self, workspace, make_nifti, data_dtype):
        shape = (5, 5, 4)
        bval, bvec, bvals, bvecs = _single_shell_gtab_files(workspace)
        tensor = np.diag([1.7e-3, 0.3e-3, 0.3e-3])
        signal = 1000 * np.exp(-bvals * np.einsum("ni,ij,nj->n", bvecs, tensor, bvecs))
        rng = np.random.default_rng(3)
        data = np.tile(signal, shape + (1,)) + rng.random(shape + (len(bvals),)) * 20
        img = nib.Nifti1Image(data.astype(data_dtype), np.eye(4))
        img.header.set_data_dtype(data_dtype)
        in_file = str(workspace / "dwi.nii.gz")
        nib.save(img, in_file)
        mask_file = make_nifti("mask.nii.gz", data=np.ones(shape, dtype=np.float32))

        node = DipyTensorFit()
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.mask = mask_file
        node.run()
        return in_file, bval, bvec, nib.load(node._list_outputs()["fa"])

    def _expected_fa(self, in_file, bval, bvec):
        from dipy.core.gradients import gradient_table
        from dipy.io.gradients import read_bvals_bvecs
        from dipy.reconst import dti

        bvals, bvecs = read_bvals_bvecs(bval, bvec)
        data = nib.load(in_file).get_fdata(dtype=np.float32)
        return dti.TensorModel(gradient_table(bvals, bvecs=bvecs)).fit(data).fa

    def test_int16_dwi_gives_an_unquantised_float32_fa(self, workspace, make_nifti):
        in_file, bval, bvec, fa = self._fit(workspace, make_nifti, np.int16)
        assert fa.get_data_dtype() == np.dtype(np.float32)
        assert fa.shape == (5, 5, 4)
        assert np.allclose(
            fa.get_fdata(), self._expected_fa(in_file, bval, bvec), atol=1e-6
        )

    def test_float32_dwi_keeps_a_float32_fa(self, workspace, make_nifti):
        _, _, _, fa = self._fit(workspace, make_nifti, np.float32)
        assert fa.get_data_dtype() == np.dtype(np.float32)
