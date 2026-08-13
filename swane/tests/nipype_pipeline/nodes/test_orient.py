"""Unit tests for :class:`swane.nipype_pipeline.nodes.Orient.Orient`.

Only the pure-Python ``aggregate_outputs`` is exercised (the ``fslorient``
executable is never invoked), so no FSL installation is required.
"""

from swane.nipype_pipeline.nodes.Orient import Orient


class TestOrientAggregateOutputs:
    """Mapping of ``fslorient`` stdout/inputs onto the interface outputs."""

    def test_get_orient_copies_stdout_to_orient(self, make_file, fake_runtime):
        """In 'get orientation' mode the stdout is exposed as ``orient``."""
        node = Orient(in_file=make_file("vol.nii.gz", "x"))
        node.inputs.get_orient = True
        outputs = node.aggregate_outputs(runtime=fake_runtime("RADIOLOGICAL"))
        assert outputs.orient == "RADIOLOGICAL"

    def test_swap_orient_reports_input_as_output_file(self, make_file, fake_runtime):
        """In 'swap orientation' mode the (in-place) input becomes ``out_file``."""
        in_file = make_file("vol.nii.gz", "x")
        node = Orient(in_file=in_file)
        node.inputs.swap_orient = True
        outputs = node.aggregate_outputs(runtime=fake_runtime(""))
        assert outputs.out_file == in_file
