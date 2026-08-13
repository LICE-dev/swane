"""Unit tests for :class:`swane.nipype_pipeline.nodes.FslNVols.FslNVols`.

Only the pure-Python ``aggregate_outputs`` is exercised (the ``fslnvols``
executable is never invoked), so no FSL installation is required.
"""

from swane.nipype_pipeline.nodes.FslNVols import FslNVols


class TestFslNVolsAggregateOutputs:
    """Parsing of the ``fslnvols`` stdout into the ``nvols`` output."""

    def test_parses_integer_stdout(self, make_file, fake_runtime):
        """A numeric stdout is parsed into the ``nvols`` integer output."""
        node = FslNVols()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        outputs = node.aggregate_outputs(runtime=fake_runtime("42"))
        assert outputs.nvols == 42

    def test_non_numeric_stdout_becomes_zero(self, make_file, fake_runtime):
        """Unparseable stdout falls back to ``0`` instead of raising."""
        node = FslNVols()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        outputs = node.aggregate_outputs(runtime=fake_runtime("not a number"))
        assert outputs.nvols == 0

    def test_forced_value_overrides_stdout(self, make_file, fake_runtime):
        """A user-provided ``force_value`` wins over the parsed stdout."""
        node = FslNVols()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        node.inputs.force_value = 7
        outputs = node.aggregate_outputs(runtime=fake_runtime("42"))
        assert outputs.nvols == 7

    def test_sentinel_minus_one_is_not_forced(self, make_file, fake_runtime):
        """``force_value == -1`` is the 'not set' sentinel and is ignored.

        The reading falls back to parsing the stdout as usual.
        """
        node = FslNVols()
        node.inputs.in_file = make_file("vol.nii.gz", "x")
        node.inputs.force_value = -1
        outputs = node.aggregate_outputs(runtime=fake_runtime("42"))
        assert outputs.nvols == 42
