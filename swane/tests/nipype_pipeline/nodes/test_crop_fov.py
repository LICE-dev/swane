"""Unit tests for :class:`swane.nipype_pipeline.nodes.CropFov.CropFov`.

The interface only uses nibabel (``load``/``save``/``conform``), so it runs
with no FSL/FreeSurfer. It leaves small volumes untouched and down-samples any
volume whose field of view exceeds ``max_dim`` mm.
"""

import os

import nibabel as nib

from swane.nipype_pipeline.nodes.CropFov import CropFov


class TestCropFov:
    def test_small_fov_is_copied_unchanged(self, workspace, make_nifti):
        """A volume within ``max_dim`` is copied through with its shape intact.

        FOV = 4 voxels * 1 mm = 4 mm, well under the 250 mm limit.
        """
        in_file = make_nifti("small.nii.gz", shape=(4, 4, 4), zooms=(1, 1, 1))
        node = CropFov()
        node.inputs.in_file = in_file
        node.inputs.max_dim = 250

        result = node.run()
        assert nib.load(result.outputs.out_file).shape == (4, 4, 4)

    def test_large_fov_is_downsampled(self, workspace, make_nifti):
        """A volume above ``max_dim`` is resampled to fit under the limit.

        FOV = 10 voxels * 30 mm = 300 mm > 250 mm. The rescale factor is
        ``(250 - 1) / 300``, so each 10-voxel axis becomes ``int(10 * .83) = 8``
        and the new FOV (8 * 30 = 240 mm) is within the limit.
        """
        in_file = make_nifti("big.nii.gz", shape=(10, 10, 10), zooms=(30, 30, 30))
        node = CropFov()
        node.inputs.in_file = in_file
        node.inputs.max_dim = 250

        result = node.run()
        out = nib.load(result.outputs.out_file)
        assert out.shape == (8, 8, 8)
        assert max(d * z for d, z in zip(out.shape, out.header.get_zooms())) <= 250

    def test_default_output_name(self, make_nifti):
        """The default output name is ``cropped_<input basename>``."""
        in_file = make_nifti("brain.nii.gz", shape=(4, 4, 4), zooms=(1, 1, 1))
        node = CropFov()
        node.inputs.in_file = in_file
        node.inputs.max_dim = 250
        out = node._gen_outfilename()
        assert os.path.basename(out) == "cropped_brain.nii.gz"
        assert os.path.isabs(out)
