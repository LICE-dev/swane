"""Unit tests for :class:`swane.nipype_pipeline.nodes.ForceOrient.ForceOrient`.

Reorientation is done with ``nibabel`` (``as_reoriented`` to the LAS layout, the
radiological RL/PA/IS convention), so both the output-name helper and the actual
reorientation are exercised here without FSL.
"""

import os

import numpy as np
import nibabel as nib

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


class TestForceOrientReorientation:
    """The actual reorientation to the LAS (radiological) layout."""

    def test_reorients_to_las(self, workspace, make_nifti):
        """A RAS input is reoriented to LAS; shape and voxel count are kept."""
        data = np.arange(64, dtype=np.float32).reshape(4, 4, 4)
        # the identity affine is a plain RAS orientation
        node = ForceOrient()
        node.inputs.in_file = make_nifti("t1.nii.gz", data=data, affine=np.eye(4))

        result = node.run()
        out = nib.load(result.outputs.out_file)

        assert nib.aff2axcodes(out.affine) == ("L", "A", "S")
        assert out.shape == (4, 4, 4)
        # data is only permuted/flipped, so the voxel values are preserved
        assert np.array_equal(
            np.sort(out.get_fdata(), axis=None), np.sort(data, axis=None)
        )
