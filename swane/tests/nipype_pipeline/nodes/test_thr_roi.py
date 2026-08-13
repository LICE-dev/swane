"""Unit tests for :class:`swane.nipype_pipeline.nodes.ThrROI.ThrROI`.

The thresholding runs on FSL; only the FSL-free output-name helper is tested.
"""

import os

from swane.nipype_pipeline.nodes.ThrROI import ThrROI


class TestThrROIOutputName:
    def test_default_name_encodes_segmentation_bounds(self, make_file):
        """The default name embeds the min/max bounds and the input basename."""
        node = ThrROI()
        node.inputs.in_file = make_file("seg.nii.gz", "x")
        node.inputs.seg_val_min = 10.0
        node.inputs.seg_val_max = 20.0
        out = node._gen_outfilename()
        assert os.path.basename(out) == "ROI_10.0_20.0_seg.nii.gz"
        assert os.path.isabs(out)

    def test_explicit_name_is_preserved(self, make_file):
        """An explicit ``out_file`` overrides the generated name."""
        node = ThrROI()
        node.inputs.in_file = make_file("seg.nii.gz", "x")
        node.inputs.seg_val_min = 1.0
        node.inputs.seg_val_max = 2.0
        node.inputs.out_file = "roi.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "roi.nii.gz"

    def test_list_outputs_matches_generated_name(self, make_file):
        """``_list_outputs`` exposes the same generated output path."""
        node = ThrROI()
        node.inputs.in_file = make_file("seg.nii.gz", "x")
        node.inputs.seg_val_min = 3.0
        node.inputs.seg_val_max = 4.0
        assert node._list_outputs()["out_file"] == node._gen_outfilename()
