"""Unit tests for
:class:`swane.nipype_pipeline.nodes.FLAT1OutliersMask.FLAT1OutliersMask`.

The mask refinement runs on FSL; only the FSL-free output-name helper is tested.
"""

import os

from swane.nipype_pipeline.nodes.FLAT1OutliersMask import FLAT1OutliersMask


class TestFLAT1OutliersMaskOutputName:
    def test_default_name_is_fixed(self, make_file):
        """With no ``out_file`` the name is the fixed refined-mask filename."""
        node = FLAT1OutliersMask()
        node.inputs.in_file = make_file("flair.nii.gz", "x")
        out = node._gen_outfilename()
        assert os.path.basename(out) == "brain_cortex_mas_refined.nii.gz"
        assert os.path.isabs(out)

    def test_explicit_name_is_preserved(self, make_file):
        """An explicit ``out_file`` overrides the fixed default name."""
        node = FLAT1OutliersMask()
        node.inputs.in_file = make_file("flair.nii.gz", "x")
        node.inputs.out_file = "refined.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "refined.nii.gz"

    def test_list_outputs_matches_generated_name(self, make_file):
        """``_list_outputs`` exposes the same generated output path."""
        node = FLAT1OutliersMask()
        node.inputs.in_file = make_file("flair.nii.gz", "x")
        assert node._list_outputs()["out_file"] == node._gen_outfilename()
