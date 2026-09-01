import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.AffineToFSL import AffineToFSL


def _write_img(path, shape, zooms):
    aff = np.diag(list(zooms) + [1.0])
    nib.Nifti1Image(np.zeros(shape, "float32"), aff).to_filename(str(path))
    return str(path)


def test_affine_to_fsl_emits_forward_and_inverse(tmp_path):
    pytest.importorskip("nitransforms")
    from nitransforms.linear import Affine

    mov = _write_img(tmp_path / "mov.nii.gz", (10, 10, 10), (2, 2, 2))
    ref = _write_img(tmp_path / "ref.nii.gz", (20, 20, 20), (1, 1, 1))
    itk = tmp_path / "aff.mat"
    Affine(np.eye(4), reference=nib.load(ref)).to_filename(
        str(itk), fmt="itk", moving=nib.load(mov)
    )

    node = AffineToFSL()
    node.inputs.in_transform = str(itk)
    node.inputs.in_fmt = "itk"
    node.inputs.source_file = mov
    node.inputs.reference_file = ref
    node.inputs.out_file = str(tmp_path / "d2r.mat")
    node.inputs.out_file_inverse = str(tmp_path / "r2d.mat")
    res = node.run()

    fwd = np.loadtxt(res.outputs.out_fsl)
    inv = np.loadtxt(res.outputs.out_fsl_inverse)
    assert fwd.shape == (4, 4)
    # the emitted inverse is the numeric inverse of the forward matrix
    assert np.allclose(fwd @ inv, np.eye(4), atol=1e-6)
