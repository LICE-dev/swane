"""Unit tests for :class:`swane.nipype_pipeline.nodes.NVols.NVols`.

``NVols`` reads the number of volumes of a 4D NIfTI through ``nibabel`` (no FSL
``fslnvols`` executable is involved), so the full interface can be exercised on
tiny synthetic volumes.
"""

from swane.nipype_pipeline.nodes.NVols import NVols


class TestNVols:
    """Volume counting and ``force_value`` handling."""

    def test_counts_4d_volumes(self, make_nifti):
        """The 4th dimension length is reported as ``nvols``."""
        node = NVols()
        node.inputs.in_file = make_nifti("vol.nii.gz", shape=(4, 4, 4, 42))
        outputs = node.run().outputs
        assert outputs.nvols == 42

    def test_3d_volume_counts_as_one(self, make_nifti):
        """A 3D image (no 4th dimension) counts as a single volume."""
        node = NVols()
        node.inputs.in_file = make_nifti("vol.nii.gz", shape=(4, 4, 4))
        outputs = node.run().outputs
        assert outputs.nvols == 1

    def test_forced_value_overrides_reading(self, make_nifti):
        """A user-provided ``force_value`` wins over the file reading."""
        node = NVols()
        node.inputs.in_file = make_nifti("vol.nii.gz", shape=(4, 4, 4, 42))
        node.inputs.force_value = 7
        outputs = node.run().outputs
        assert outputs.nvols == 7

    def test_sentinel_minus_one_is_not_forced(self, make_nifti):
        """``force_value == -1`` is the 'not set' sentinel and is ignored.

        The count falls back to reading the file as usual.
        """
        node = NVols()
        node.inputs.in_file = make_nifti("vol.nii.gz", shape=(4, 4, 4, 42))
        node.inputs.force_value = -1
        outputs = node.run().outputs
        assert outputs.nvols == 42
