"""Unit tests for :class:`swane.nipype_pipeline.nodes.AsymmetryIndex.AsymmetryIndex`.

The heavy lifting uses FSL ``BinaryMaths``; only the FSL-free output-name
helpers are exercised here.
"""

import os

from swane.nipype_pipeline.nodes.AsymmetryIndex import AsymmetryIndex


class TestAsymmetryIndexOutputName:
    def test_default_name_prefixes_input(self, make_file):
        """The default output name is ``Aindex_<input basename>``."""
        node = AsymmetryIndex()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        out = node._gen_outfilename()
        assert os.path.basename(out) == "Aindex_t1.nii.gz"
        assert os.path.isabs(out)

    def test_explicit_name_is_preserved(self, make_file):
        """An explicit ``out_file`` overrides the generated name."""
        node = AsymmetryIndex()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        node.inputs.out_file = "custom.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "custom.nii.gz"

    def test_list_outputs_matches_generated_name(self, make_file):
        """``_list_outputs`` exposes the same generated output path."""
        node = AsymmetryIndex()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        assert node._list_outputs()["out_file"] == node._gen_outfilename()
