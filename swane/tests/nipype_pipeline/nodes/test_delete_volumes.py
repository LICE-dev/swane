"""Unit tests for :class:`swane.nipype_pipeline.nodes.DeleteVolumes.DeleteVolumes`.

Only the FSL-free parts are exercised: the volume-count arithmetic in
``_list_outputs`` and the pass-through branch of ``_run_interface`` that just
copies the file when nothing has to be trimmed.
"""

import os

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


class TestDeleteVolumesNoTrim:
    """The pass-through branch that avoids the FSL ``ExtractROI`` call."""

    def test_zero_trim_copies_the_file(self, workspace, make_file):
        """When nothing is trimmed the input is copied verbatim, no FSL needed.

        The input lives in a sub-folder so the working-dir output path differs
        from the source (as it does when the node runs in its own directory).
        """
        in_file = make_file("input/bold.nii.gz", "payload")
        node = DeleteVolumes()
        node.inputs.in_file = in_file
        node.inputs.nvols = 8
        node.inputs.del_start_vols = 0
        node.inputs.del_end_vols = 0

        result = node.run()

        assert os.path.exists(result.outputs.out_file)
        with open(result.outputs.out_file) as handle:
            assert handle.read() == "payload"
        assert result.outputs.nvols == 8
