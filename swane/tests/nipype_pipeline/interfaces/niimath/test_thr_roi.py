"""Unit tests for :class:`swane.nipype_pipeline.interfaces.niimath.ThrROI.ThrROI`.

``ThrROI`` subclasses the niimath-backed ``ImageMaths`` interface and only
customises ``_parse_inputs`` to build the thresholding operation from the
segmentation bounds. That string assembly is pure Python, so it is exercised
here on the command line without running niimath (the actual thresholding is
checked in ``test_niimath_command_inputs.py``).
"""

from swane.nipype_pipeline.interfaces.niimath.ThrROI import ThrROI


class TestThrROIOpString:
    """The ``op_string`` built from the ``seg_val_min``/``seg_val_max`` bounds."""

    def test_op_string_encodes_bounds(self, make_file):
        """The command line carries a ``-thr <min> -uthr <max> -bin`` operation."""
        node = ThrROI()
        node.inputs.in_file = make_file("seg.nii.gz", "x")
        node.inputs.seg_val_min = 10.0
        node.inputs.seg_val_max = 20.0
        assert "-thr 10.0000000000 -uthr 20.0000000000 -bin" in node.cmdline

    def test_op_string_uses_full_precision(self, make_file):
        """Non-integer bounds are kept at 10 decimal places, min then max."""
        node = ThrROI()
        node.inputs.in_file = make_file("seg.nii.gz", "x")
        node.inputs.seg_val_min = 1.5
        node.inputs.seg_val_max = 2.25
        assert "-thr 1.5000000000 -uthr 2.2500000000 -bin" in node.cmdline
