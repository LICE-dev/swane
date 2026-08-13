"""Unit tests for :class:`swane.nipype_pipeline.nodes.ZIntNorm.ZIntNorm`.

The interface applies a within-image z-score normalisation using only
numpy/nibabel, so it runs with no FSL/FreeSurfer.
"""

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.ZIntNorm import ZIntNorm


class TestZIntNorm:
    def test_normalises_to_zero_mean_unit_std(self, workspace, make_nifti):
        """Voxels are rescaled to ``(x - mean) / std`` over the >0 mask.

        With every voxel positive the mask is the whole image, so the output
        has (numerically) zero mean and unit standard deviation.
        """
        data = np.arange(1, 28, dtype=np.float32).reshape(3, 3, 3)
        in_file = make_nifti("img.nii.gz", data=data)
        node = ZIntNorm()
        node.inputs.in_file = in_file

        result = node.run()
        out = nib.load(result.outputs.out_file).get_fdata(dtype=np.float32)

        expected = (data - data.mean()) / data.std()
        assert np.allclose(out, expected, atol=1e-5)
        assert np.isclose(out.mean(), 0.0, atol=1e-5)
        assert np.isclose(out.std(), 1.0, atol=1e-5)

    def test_explicit_mask_restricts_statistics(self, workspace, make_nifti):
        """A provided ``mask_file`` selects which voxels define mean/std.

        The normalisation is still applied to the whole image, but mean and std
        are computed only over the masked voxels.
        """
        data = np.arange(1, 28, dtype=np.float32).reshape(3, 3, 3)
        mask = np.zeros((3, 3, 3), dtype=np.float32)
        mask[:, :, 0] = 1  # first slice only
        in_file = make_nifti("img.nii.gz", data=data)
        mask_file = make_nifti("mask.nii.gz", data=mask)

        node = ZIntNorm()
        node.inputs.in_file = in_file
        node.inputs.mask_file = mask_file
        result = node.run()
        out = nib.load(result.outputs.out_file).get_fdata(dtype=np.float32)

        masked_vals = data[mask > 0]
        expected = (data - masked_vals.mean()) / masked_vals.std()
        assert np.allclose(out, expected, atol=1e-5)

    def test_zero_variance_raises(self, workspace, make_nifti):
        """A constant image has zero std and raises a clear ``RuntimeError``."""
        data = np.full((3, 3, 3), 5.0, dtype=np.float32)
        in_file = make_nifti("flat.nii.gz", data=data)
        node = ZIntNorm()
        node.inputs.in_file = in_file

        with pytest.raises(RuntimeError):
            node.run()

    def test_default_output_name(self, make_nifti):
        """The default output name is ``normalized_<input basename>``."""
        import os

        in_file = make_nifti("t1.nii.gz", shape=(2, 2, 2))
        node = ZIntNorm()
        node.inputs.in_file = in_file
        out = node._gen_outfilename()
        assert os.path.basename(out) == "normalized_t1.nii.gz"
