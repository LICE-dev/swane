"""Unit tests for :class:`swane.nipype_pipeline.nodes.GetNiftiTR.GetNiftiTR`.

Only the pure-Python ``aggregate_outputs`` is exercised (the ``fslval``
executable is never invoked), so no FSL installation is required.
"""

from swane.nipype_pipeline.nodes.GetNiftiTR import GetNiftiTR


class TestGetNiftiTRAggregateOutputs:
    """Parsing of the ``fslval ... pixdim4`` stdout into the ``TR`` output."""

    def test_parses_float_stdout(self, make_file, fake_runtime):
        """A numeric stdout is parsed into the ``TR`` float output."""
        node = GetNiftiTR()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        outputs = node.aggregate_outputs(runtime=fake_runtime("2.5"))
        assert outputs.TR == 2.5

    def test_non_numeric_stdout_becomes_zero(self, make_file, fake_runtime):
        """Unparseable stdout falls back to ``0.0`` instead of raising."""
        node = GetNiftiTR()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        outputs = node.aggregate_outputs(runtime=fake_runtime("N/A"))
        assert outputs.TR == 0.0

    def test_forced_value_overrides_stdout(self, make_file, fake_runtime):
        """A user-provided ``force_value`` wins over the parsed stdout."""
        node = GetNiftiTR()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        node.inputs.force_value = 3.0
        outputs = node.aggregate_outputs(runtime=fake_runtime("2.5"))
        assert outputs.TR == 3.0

    def test_sentinel_minus_one_is_not_forced(self, make_file, fake_runtime):
        """``force_value == -1`` is the 'not set' sentinel and is ignored."""
        node = GetNiftiTR()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        node.inputs.force_value = -1
        outputs = node.aggregate_outputs(runtime=fake_runtime("2.5"))
        assert outputs.TR == 2.5
