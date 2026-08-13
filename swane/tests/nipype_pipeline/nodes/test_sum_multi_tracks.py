"""Unit tests for :class:`swane.nipype_pipeline.nodes.SumMultiTracks.SumMultiTracks`.

The volume summation runs on FSL ``BinaryMaths``; only the FSL-free output-name
helpers are tested here.
"""

import os

from swane.nipype_pipeline.nodes.SumMultiTracks import SumMultiTracks


class TestSumMultiTracksOutputNames:
    def test_default_track_sum_name(self):
        """With no ``out_file`` the summed-track output defaults to ``sum.nii.gz``."""
        node = SumMultiTracks()
        out = node._gen_outfilename()
        assert os.path.basename(out) == "sum.nii.gz"
        assert os.path.isabs(out)

    def test_waytotal_name_derived_from_out_file(self):
        """The waytotal file name is ``<out_file stem>_waytotal``."""
        node = SumMultiTracks()
        node.inputs.out_file = "tracks.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "tracks.nii.gz"
        assert os.path.basename(node._gen_waytotal_outfilename()) == "tracks_waytotal"

    def test_list_outputs_reports_both_files(self):
        """``_list_outputs`` returns both the summed-track and waytotal paths."""
        node = SumMultiTracks()
        node.inputs.out_file = "tracks.nii.gz"
        outputs = node._list_outputs()
        assert os.path.basename(outputs["out_file"]) == "tracks.nii.gz"
        assert os.path.basename(outputs["waytotal_sum"]) == "tracks_waytotal"
