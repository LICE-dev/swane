"""Unit tests for :class:`swane.nipype_pipeline.nodes.ForceOrient.ForceOrient`.

Reorientation runs on FSL ``SwapDimensions``; only the FSL-free output-name
helper is tested.
"""

import os

from swane.nipype_pipeline.nodes.ForceOrient import ForceOrient


class TestForceOrientOutputName:
    def test_default_name_matches_input_basename(self, make_file):
        """The default output keeps the input basename (written in the work dir)."""
        node = ForceOrient()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        out = node._gen_outfilename()
        assert os.path.basename(out) == "t1.nii.gz"
        assert os.path.isabs(out)

    def test_explicit_name_is_preserved(self, make_file):
        """An explicit ``out_file`` overrides the default name."""
        node = ForceOrient()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        node.inputs.out_file = "oriented.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "oriented.nii.gz"

    def test_list_outputs_matches_generated_name(self, make_file):
        """``_list_outputs`` exposes the same generated output path."""
        node = ForceOrient()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        assert node._list_outputs()["out_file"] == node._gen_outfilename()
