"""Unit tests for :class:`swane.nipype_pipeline.nodes.DeleteVolumes.DeleteVolumes`.

Only the FSL-free parts are exercised: the volume-count arithmetic in
``_list_outputs`` and the pass-through branch of ``_run_interface`` that just
copies the file when nothing has to be trimmed.
"""

import os

import nibabel as nib

from swane.nipype_pipeline.nodes.DeleteVolumes import DeleteVolumes


class TestDeleteVolumesOutputs:
    """The ``_list_outputs`` volume-count bookkeeping."""

    def test_new_volume_count_subtracts_both_ends(self, make_file):
        """Output ``nvols`` is the input count minus the trimmed head/tail."""
        node = DeleteVolumes()
        node.inputs.in_file = make_file("bold.nii.gz", "x")
        node.inputs.nvols = 100
        node.inputs.del_start_vols = 5
        node.inputs.del_end_vols = 3

        outputs = node._list_outputs()
        assert outputs["nvols"] == 92

    def test_output_basename_matches_input(self, make_file):
        """The output keeps the input's basename (in the working dir)."""
        node = DeleteVolumes()
        node.inputs.in_file = make_file("bold.nii.gz", "x")
        node.inputs.nvols = 10
        node.inputs.del_start_vols = 0
        node.inputs.del_end_vols = 0

        outputs = node._list_outputs()
        assert os.path.basename(outputs["out_file"]) == "bold.nii.gz"
        assert os.path.isabs(outputs["out_file"])


class TestDeleteVolumesRun:
    """The nibabel-based volume extraction in ``_run_interface``."""

    def test_zero_trim_keeps_all_volumes(self, workspace, make_nifti):
        """When nothing is trimmed every input volume is kept, no FSL needed.

        The input lives in a sub-folder so the working-dir output path differs
        from the source (as it does when the node runs in its own directory).
        """
        in_file = make_nifti("input/bold.nii.gz", shape=(4, 4, 4, 8))
        node = DeleteVolumes()
        node.inputs.in_file = in_file
        node.inputs.nvols = 8
        node.inputs.del_start_vols = 0
        node.inputs.del_end_vols = 0

        result = node.run()

        assert os.path.exists(result.outputs.out_file)
        assert result.outputs.nvols == 8
        assert nib.load(result.outputs.out_file).shape == (4, 4, 4, 8)

    def test_trims_head_and_tail(self, workspace, make_nifti):
        """Volumes are removed from both ends via nibabel (no FSL ExtractROI)."""
        in_file = make_nifti("input/bold.nii.gz", shape=(4, 4, 4, 8))
        node = DeleteVolumes()
        node.inputs.in_file = in_file
        node.inputs.nvols = 8
        node.inputs.del_start_vols = 2
        node.inputs.del_end_vols = 1

        result = node.run()

        assert result.outputs.nvols == 5
        assert nib.load(result.outputs.out_file).shape == (4, 4, 4, 5)
