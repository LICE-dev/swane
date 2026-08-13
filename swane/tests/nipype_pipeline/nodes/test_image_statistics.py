"""Unit tests for :class:`swane.nipype_pipeline.nodes.ImageStatistics.ImageStatistics`.

The node computes intensity statistics with ``nibabel``/``numpy`` only, so the
whole interface is exercised on tiny synthetic volumes without FSL.

Conventions under test (see the node docstring):

* ``mean``/``std``/``n_voxels``/``volume`` describe the **non-zero** voxels of
  the domain; ``std`` uses the sample (N-1) denominator
* ``min_value``/``max_value``/percentiles describe **all** voxels of the domain
* the domain is the whole image, or the ``mask_file`` voxels (> 0) when given
* percentiles use the nearest-rank definition (numpy ``method="higher"``)
"""

import numpy as np
import pytest

from swane.nipype_pipeline.nodes.ImageStatistics import ImageStatistics


class TestImageStatisticsWholeImage:
    """Statistics over the whole image (no mask)."""

    def test_non_zero_statistics_and_percentiles(self, make_nifti):
        """Non-zero mean/std/count/volume, plus full-domain min/max/percentiles."""
        data = np.array([0, 1, 2, 3, 4, 0, 0, 0], dtype=np.float32).reshape(2, 2, 2)
        node = ImageStatistics()
        node.inputs.in_file = make_nifti("img.nii.gz", data=data, zooms=(2.0, 2.0, 2.0))
        node.inputs.percentiles = [0.0, 50.0, 100.0]
        outputs = node.run().outputs

        # non-zero voxels are [1, 2, 3, 4]
        assert outputs.mean == pytest.approx(2.5)
        assert outputs.std == pytest.approx(1.2909944487358056)
        assert outputs.n_voxels == 4
        # 4 non-zero voxels * (2*2*2) mm3 each
        assert outputs.volume == pytest.approx(32.0)
        # min/max/percentiles include the zero background
        assert outputs.min_value == pytest.approx(0.0)
        assert outputs.max_value == pytest.approx(4.0)
        assert outputs.percentile_values == pytest.approx([0.0, 1.0, 4.0])

    def test_all_zero_image_is_handled(self, make_nifti):
        """An all-zero image yields zeroed statistics instead of raising."""
        data = np.zeros((2, 2, 2), dtype=np.float32)
        node = ImageStatistics()
        node.inputs.in_file = make_nifti("zero.nii.gz", data=data)
        outputs = node.run().outputs

        assert outputs.mean == 0.0
        assert outputs.std == 0.0
        assert outputs.n_voxels == 0
        assert outputs.volume == 0.0
        assert outputs.min_value == 0.0
        assert outputs.max_value == 0.0


class TestImageStatisticsMasked:
    """Statistics restricted to a mask."""

    def test_mask_restricts_the_domain(self, make_nifti):
        """Only voxels where the mask is > 0 contribute to the statistics."""
        data = np.arange(1, 9, dtype=np.float32).reshape(2, 2, 2)  # 1..8
        mask = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.float32).reshape(2, 2, 2)
        node = ImageStatistics()
        node.inputs.in_file = make_nifti("img.nii.gz", data=data)
        node.inputs.mask_file = make_nifti("mask.nii.gz", data=mask)
        outputs = node.run().outputs

        # masked, non-zero voxels are [1, 2, 3, 4]
        assert outputs.mean == pytest.approx(2.5)
        assert outputs.n_voxels == 4
        assert outputs.min_value == pytest.approx(1.0)
        assert outputs.max_value == pytest.approx(4.0)
