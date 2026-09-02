"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyTensorFit.DipyTensorFit`.

Runs dipy's real tensor model on tiny synthetic gradient data -- cheap enough
at this size -- and checks the FA map's shape and finiteness, plus the OMP
thread pin (this node is declared ``n_procs=1`` and must not let numpy/BLAS
silently use more).
"""

import os

import numpy as np
import nibabel as nib

from swane.nipype_pipeline.nodes.DipyTensorFit import DipyTensorFit, OMP_THREADS_VAR


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
