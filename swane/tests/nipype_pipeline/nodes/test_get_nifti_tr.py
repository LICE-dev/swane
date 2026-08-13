"""Unit tests for :class:`swane.nipype_pipeline.nodes.GetNiftiTR.GetNiftiTR`.

``GetNiftiTR`` reads the repetition time straight from the NIfTI header
(``pixdim[4]``) through ``nibabel``, so no FSL ``fslval`` executable is
involved and the full interface runs on tiny synthetic volumes.
"""

from swane.nipype_pipeline.nodes.GetNiftiTR import GetNiftiTR


class TestGetNiftiTR:
    """Reading of the repetition time and ``force_value`` handling."""

    def test_reads_tr_from_header(self, make_nifti):
        """The 4th ``pixdim`` (the time step) is reported as ``TR``."""
        node = GetNiftiTR()
        node.inputs.in_file = make_nifti(
            "bold.nii.gz", shape=(4, 4, 4, 2), zooms=(2.0, 2.0, 2.0, 2.5)
        )
        outputs = node.run().outputs
        assert outputs.TR == 2.5

    def test_forced_value_overrides_reading(self, make_nifti):
        """A user-provided ``force_value`` wins over the header reading."""
        node = GetNiftiTR()
        node.inputs.in_file = make_nifti(
            "bold.nii.gz", shape=(4, 4, 4, 2), zooms=(2.0, 2.0, 2.0, 2.5)
        )
        node.inputs.force_value = 3.0
        outputs = node.run().outputs
        assert outputs.TR == 3.0

    def test_sentinel_minus_one_is_not_forced(self, make_nifti):
        """``force_value == -1`` is the 'not set' sentinel and is ignored.

        The reading falls back to the header value as usual.
        """
        node = GetNiftiTR()
        node.inputs.in_file = make_nifti(
            "bold.nii.gz", shape=(4, 4, 4, 2), zooms=(2.0, 2.0, 2.0, 2.5)
        )
        node.inputs.force_value = -1
        outputs = node.run().outputs
        assert outputs.TR == 2.5
