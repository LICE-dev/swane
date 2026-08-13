"""Unit tests for :class:`swane.nipype_pipeline.nodes.Zscore.Zscore`.

The z-score map is built with FSL; only the FSL-free output-name helper is
tested here.
"""

import os

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
