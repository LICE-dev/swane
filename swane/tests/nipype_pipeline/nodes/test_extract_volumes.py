"""Unit tests for :mod:`swane.nipype_pipeline.nodes.ExtractVolumes`.

Both the pure ``extract_volumes`` helper and the ``ExtractVolumes`` interface
slice the time axis with ``nibabel``, so everything runs on tiny synthetic 4D
volumes without any FSL executable.
"""

import os

import numpy as np
import nibabel as nib

from swane.nipype_pipeline.nodes.ExtractVolumes import (
    ExtractVolumes,
    extract_volumes,
)


class TestExtractVolumesHelper:
    """The ``extract_volumes`` slicing helper."""

    def _img(self):
        # each volume filled with its own index so slices are identifiable
        data = np.zeros((2, 2, 2, 5), dtype=np.float32)
        for v in range(5):
            data[..., v] = v
        return nib.Nifti1Image(data, np.eye(4))

    def test_single_volume_is_returned_as_3d(self):
        """Extracting one volume drops the time axis (3D output)."""
        out = extract_volumes(self._img(), start_volume=2, num_volumes=1)
        assert out.shape == (2, 2, 2)
        assert np.all(out.get_fdata() == 2)

    def test_range_keeps_time_axis(self):
        """Extracting several volumes keeps a 4D image with the right slice."""
        out = extract_volumes(self._img(), start_volume=1, num_volumes=3)
        assert out.shape == (2, 2, 2, 3)
        assert [out.get_fdata()[0, 0, 0, i] for i in range(3)] == [1, 2, 3]


class TestExtractVolumesInterface:
    """The ``ExtractVolumes`` node wrapping the helper."""

    def test_extracts_requested_range(self, workspace, make_nifti):
        """The node writes a NIfTI with only the requested volumes."""
        node = ExtractVolumes()
        node.inputs.in_file = make_nifti("bold.nii.gz", shape=(2, 2, 2, 6))
        node.inputs.start_volume = 1
        node.inputs.num_volumes = 2
        result = node.run()
        assert nib.load(result.outputs.out_file).shape == (2, 2, 2, 2)

    def test_default_extracts_first_volume(self, workspace, make_nifti):
        """Defaults (start 0, count 1) return the first volume as a 3D image."""
        node = ExtractVolumes()
        node.inputs.in_file = make_nifti("bold.nii.gz", shape=(2, 2, 2, 6))
        result = node.run()
        assert nib.load(result.outputs.out_file).shape == (2, 2, 2)

    def test_default_output_basename_is_prefixed(self, make_nifti):
        """The generated output name prefixes the input basename with ``roi_``."""
        node = ExtractVolumes()
        node.inputs.in_file = make_nifti("bold.nii.gz", shape=(2, 2, 2, 6))
        out = node._gen_outfilename()
        assert os.path.basename(out) == "roi_bold.nii.gz"
        assert os.path.isabs(out)
