"""Unit tests for :class:`swane.nipype_pipeline.nodes.Zscore.Zscore`.

The z-score map is computed with ``nibabel``/``numpy`` only (no FSL): each voxel
becomes ``(value - mean) / std`` where ``mean``/``std`` are taken over the
non-zero voxels inside the ROI (sample std, N-1). Both the output-name helper
and the arithmetic are exercised here.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.Zscore import Zscore


class TestZscoreOutputName:
    def test_default_name_prefixes_input(self, make_file):
        """The default output name is ``zscore_<input basename>``."""
        node = Zscore()
        node.inputs.in_file = make_file("map.nii.gz", "x")
        out = node._gen_outfilename()
        assert os.path.basename(out) == "zscore_map.nii.gz"
        assert os.path.isabs(out)

    def test_explicit_name_is_preserved(self, make_file):
        """An explicit ``out_file`` overrides the generated name."""
        node = Zscore()
        node.inputs.in_file = make_file("map.nii.gz", "x")
        node.inputs.out_file = "z.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "z.nii.gz"

    def test_list_outputs_matches_generated_name(self, make_file):
        """``_list_outputs`` exposes the same generated output path."""
        node = Zscore()
        node.inputs.in_file = make_file("map.nii.gz", "x")
        assert node._list_outputs()["out_file"] == node._gen_outfilename()


class TestZscoreComputation:
    """The ``(value - mean) / std`` normalisation over the ROI statistics."""

    def test_zscore_values(self, workspace, make_nifti):
        # ROI covers the first four voxels, values [1, 2, 3, 4]:
        #   mean = 2.5, sample std (ddof=1) = 1.2909944487358056
        in_data = np.array([1, 2, 3, 4, 2.5, 5, 0, 8], dtype=np.float32).reshape(
            2, 2, 2
        )
        mask = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.float32).reshape(2, 2, 2)
        node = Zscore()
        node.inputs.in_file = make_nifti("map.nii.gz", data=in_data)
        node.inputs.ROI_file = make_nifti("roi.nii.gz", data=mask)

        result = node.run()
        out = nib.load(result.outputs.out_file).get_fdata().ravel()

        std = 1.2909944487358056
        assert out[0] == pytest.approx((1 - 2.5) / std, rel=1e-5)
        assert out[3] == pytest.approx((4 - 2.5) / std, rel=1e-5)
        # a voxel equal to the ROI mean maps to 0 even outside the ROI
        assert out[4] == pytest.approx(0.0, abs=1e-5)

    def test_zero_std_raises(self, workspace, make_nifti):
        """A constant ROI has zero standard deviation and is rejected."""
        in_data = np.full((2, 2, 2), 5.0, dtype=np.float32)
        mask = np.ones((2, 2, 2), dtype=np.float32)
        node = Zscore()
        node.inputs.in_file = make_nifti("map.nii.gz", data=in_data)
        node.inputs.ROI_file = make_nifti("roi.nii.gz", data=mask)

        with pytest.raises(RuntimeError):
            node.run()
