"""Unit tests for
:class:`swane.nipype_pipeline.nodes.SegmentEndocranium.SegmentEndocranium`.

The real command drives 3D Slicer; only the FSL/Slicer-free output-name helper
is tested here (``out_file`` is a ``genfile`` with a fixed name).
"""

import os

from swane.nipype_pipeline.nodes.SegmentEndocranium import SegmentEndocranium


class TestSegmentEndocraniumOutputName:
    def test_genfile_returns_fixed_mask_name(self):
        """The generated ``out_file`` name is the fixed inskull-mask filename."""
        node = SegmentEndocranium()
        out = node._gen_filename("out_file")
        assert os.path.basename(out) == "inskull_mask.nii.gz"
        assert os.path.isabs(out)

    def test_genfile_unknown_name_returns_none(self):
        """Only ``out_file`` is generated; other names return ``None``."""
        node = SegmentEndocranium()
        assert node._gen_filename("something_else") is None

    def test_list_outputs_uses_generated_name(self):
        """``_list_outputs`` reports the generated (genfile) mask path."""
        node = SegmentEndocranium()
        outputs = node._list_outputs()
        assert os.path.basename(outputs["out_file"]) == "inskull_mask.nii.gz"
