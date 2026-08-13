"""Unit tests for :class:`swane.nipype_pipeline.nodes.SumMultiTracks.SumMultiTracks`.

The node sums several tractography path maps with ``nibabel``/``numpy`` and adds
up the companion ``waytotal`` counts (no FSL). Both the output-name helpers and
the actual summation are exercised here.
"""

import os

import numpy as np
import nibabel as nib

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


class TestSumMultiTracksComputation:
    """Voxel-wise summation of the path maps and of the waytotal counts."""

    def test_sums_path_maps_and_waytotals(self, workspace, make_nifti, make_file):
        p0 = make_nifti("p0.nii.gz", data=np.ones((2, 2, 2), dtype=np.float32))
        p1 = make_nifti("p1.nii.gz", data=np.full((2, 2, 2), 2.0, dtype=np.float32))
        w0 = make_file("w0.txt", "10")
        w1 = make_file("w1.txt", "20")

        node = SumMultiTracks()
        node.inputs.path_files = [p0, p1]
        node.inputs.waytotal_files = [w0, w1]

        result = node.run()

        # voxel-wise 1 + 2 = 3 everywhere
        assert np.all(nib.load(result.outputs.out_file).get_fdata() == 3)
        # 10 + 20 = 30
        with open(result.outputs.waytotal_sum) as handle:
            assert handle.read().strip() == "30"
