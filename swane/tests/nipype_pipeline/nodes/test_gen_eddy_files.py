"""Unit tests for :class:`swane.nipype_pipeline.nodes.GenEddyFiles.GenEddyFiles`.

Despite the FSL-flavoured disclaimer, the interface is pure Python: it reads a
``.bval`` file and writes the ``index``/``acqp`` text files Eddy expects.
"""

from swane.nipype_pipeline.nodes.GenEddyFiles import GenEddyFiles


class TestGenEddyFiles:
    """Generation of the Eddy ``index`` and ``acqp`` companion files."""

    def test_index_has_one_entry_per_bval(self, workspace, make_file):
        """The ``index`` file holds a single ``1`` per b-value in the input."""
        bval = make_file("dwi.bval", "0 1000 2000 0 1000")  # 5 values
        node = GenEddyFiles()
        node.inputs.bval = bval

        result = node.run()

        with open(result.outputs.index) as handle:
            entries = handle.read().split()
        assert entries == ["1", "1", "1", "1", "1"]

    def test_acqp_has_fixed_single_line(self, workspace, make_file):
        """The ``acqp`` file is a fixed single acquisition-parameters line."""
        bval = make_file("dwi.bval", "0 1000")
        node = GenEddyFiles()
        node.inputs.bval = bval

        result = node.run()

        with open(result.outputs.acqp) as handle:
            assert handle.read() == "0 1 0 0.05"

    def test_empty_bval_yields_empty_index(self, workspace, make_file):
        """An empty b-value file produces an empty ``index`` (boundary case)."""
        bval = make_file("dwi.bval", "")
        node = GenEddyFiles()
        node.inputs.bval = bval

        result = node.run()

        with open(result.outputs.index) as handle:
            assert handle.read().split() == []
