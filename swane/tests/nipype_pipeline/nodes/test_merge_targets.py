"""Unit tests for :class:`swane.nipype_pipeline.nodes.MergeTargets.MergeTargets`.

Pure Python: writes the list of input paths, one per line, to a text file.
"""

import os

from swane.nipype_pipeline.nodes.MergeTargets import MergeTargets


class TestMergeTargets:
    """Serialisation of a list of target files into a newline-separated txt."""

    def test_writes_paths_one_per_line(self, workspace, make_file):
        """Each input path is written on its own line, in order."""
        a = make_file("a.nii.gz", "a")
        b = make_file("b.nii.gz", "b")
        node = MergeTargets()
        node.inputs.target_files = [a, b]

        result = node.run()

        with open(result.outputs.out_file) as handle:
            assert handle.read() == "\n".join([a, b])

    def test_default_output_name_is_targets_txt(self, make_file):
        """With no ``out_file`` the generated name defaults to ``targets.txt``."""
        node = MergeTargets()
        node.inputs.target_files = [make_file("a.nii.gz", "a")]
        out = node._gen_outfilename()
        assert os.path.basename(out) == "targets.txt"
        assert os.path.isabs(out)

    def test_explicit_output_name_is_preserved(self, make_file):
        """An explicit ``out_file`` is honoured (only its basename is pinned)."""
        node = MergeTargets()
        node.inputs.target_files = [make_file("a.nii.gz", "a")]
        node.inputs.out_file = "custom_targets.txt"
        out = node._gen_outfilename()
        assert os.path.basename(out) == "custom_targets.txt"
