"""Unit tests for :class:`swane.nipype_pipeline.interfaces.geometry.CropFov.CropFov`.

The interface only uses nibabel, so it runs with no FSL/FreeSurfer. It leaves
volumes within ``max_dim`` mm untouched and crops every axis whose field of
view exceeds ``max_dim`` to at most ``max_dim`` mm: a plain voxel subset, with
no resampling and no reorientation, so the reference keeps its LAS layout and
its intensities. The crop exists for FreeSurfer: recon-all stops on a
conformed field of view above 256 mm, which the heavy test checks with the
real recon-all.
"""

import os
import subprocess

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.interfaces.geometry.CropFov import CropFov


def _las_affine(zooms, rotation=None):
    affine = np.eye(4)
    axes = np.diag([-1.0, 1.0, 1.0])
    if rotation is not None:
        axes = rotation @ axes
    affine[:3, :3] = axes @ np.diag(zooms)
    affine[:3, 3] = [70.0, -95.0, -60.0]
    return affine


def _save(path, data, affine, dtype=np.int16):
    img = nib.Nifti1Image(data.astype(dtype), affine)
    img.header.set_data_dtype(dtype)
    img.set_qform(affine, code=1)
    img.set_sform(affine, code=1)
    nib.save(img, path)
    return str(path)


def _run(in_file, max_dim=256):
    node = CropFov()
    node.inputs.in_file = in_file
    node.inputs.max_dim = max_dim
    return nib.load(node.run().outputs.out_file)


def _source_index(out_img, in_img):
    """Integer voxel offset of the output grid inside the input grid."""
    offset = np.linalg.inv(in_img.affine) @ out_img.affine @ [0.0, 0.0, 0.0, 1.0]
    rounded = np.round(offset[:3])
    assert np.allclose(offset[:3], rounded, atol=1e-4), "not a voxel subset"
    return rounded.astype(int)


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
        with open(in_file, "rb") as src, open(result.outputs.out_file, "rb") as dst:
            assert src.read() == dst.read()

    def test_large_fov_is_cropped(self, workspace, make_nifti):
        """A volume above ``max_dim`` keeps floor(max_dim / zoom) voxels.

        FOV = 10 voxels * 30 mm = 300 mm > 250 mm: 8 voxels (240 mm) remain on
        each axis, as an exact subset of the input voxels.
        """
        data = np.arange(1000, dtype=np.float32).reshape(10, 10, 10)
        in_file = make_nifti("big.nii.gz", data=data, zooms=(30, 30, 30))
        out = _run(in_file, max_dim=250)
        assert out.shape == (8, 8, 8)
        assert max(d * z for d, z in zip(out.shape, out.header.get_zooms())) <= 250
        i, j, k = _source_index(out, nib.load(in_file))
        assert np.array_equal(out.get_fdata(), data[i : i + 8, j : j + 8, k : k + 8])

    def test_default_output_name(self, make_nifti):
        """The default output name is ``cropped_<input basename>``."""
        in_file = make_nifti("brain.nii.gz", shape=(4, 4, 4), zooms=(1, 1, 1))
        node = CropFov()
        node.inputs.in_file = in_file
        node.inputs.max_dim = 250
        out = node._gen_outfilename()
        assert os.path.basename(out) == "cropped_brain.nii.gz"
        assert os.path.isabs(out)


class TestCropFovIsACrop:
    """The crop keeps the reference's grid: no resampling, no reorientation,
    each oversized axis cut on its own to at most ``max_dim`` mm. The previous
    implementation resampled with nibabel ``conform``: RAS output, cubic
    interpolation on a grid shifted by half a voxel, and the largest axis'
    shrink factor applied to every oversized axis (a 300 x 260 mm plane became
    255 x 221 mm instead of 256 x 256 mm)."""

    def test_each_oversized_axis_is_cut_on_its_own(self, workspace):
        # 300 x 260 x 200 mm at 5 mm: x and y exceed 256 mm, z does not.
        rng = np.random.default_rng(0)
        data = rng.integers(0, 1000, size=(60, 52, 40))
        in_file = _save(workspace / "ref.nii.gz", data, _las_affine((5.0, 5.0, 5.0)))
        in_img = nib.load(in_file)

        out = _run(in_file)

        assert out.shape == (51, 51, 40)
        assert nib.aff2axcodes(out.affine) == ("L", "A", "S")
        assert np.allclose(out.affine[:3, :3], in_img.affine[:3, :3])
        i, j, k = _source_index(out, in_img)
        assert k == 0
        assert np.array_equal(
            np.asanyarray(out.dataobj), data[i : i + 51, j : j + 51, k : k + 40]
        )

    def test_header_is_preserved(self, workspace):
        data = np.random.default_rng(1).integers(0, 1000, size=(60, 52, 40))
        in_file = _save(workspace / "ref.nii.gz", data, _las_affine((5.0, 5.0, 5.0)))

        out = _run(in_file)

        assert out.get_data_dtype() == np.dtype(np.int16)
        assert int(out.header["qform_code"]) == 1
        assert int(out.header["sform_code"]) == 1
        assert np.allclose(out.header.get_zooms(), (5.0, 5.0, 5.0))

    def test_anisotropic_voxels_keep_up_to_max_dim_mm(self, workspace):
        # 288 x 0.9375 mm = 270 mm -> floor(256 / 0.9375) = 273 voxels (255.9 mm)
        data = np.ones((288, 6, 6))
        in_file = _save(workspace / "ref.nii.gz", data, _las_affine((0.9375, 1.2, 1.2)))
        out = _run(in_file)
        assert out.shape == (273, 6, 6)
        assert out.shape[0] * out.header.get_zooms()[0] <= 256

    def test_window_follows_the_head_not_the_fov_centre(self, workspace):
        """A head off-centre in a wide field of view is kept whole: the window
        is centred on the intensity centre of mass, not on the image centre
        (which would cut the head's far side here)."""
        data = np.zeros((60, 20, 20))
        data[46:59, 5:15, 5:15] = 500  # head near the high-x edge
        in_file = _save(workspace / "ref.nii.gz", data, _las_affine((5.0, 5.0, 5.0)))
        out = _run(in_file)
        assert out.shape == (51, 20, 20)
        assert np.asanyarray(out.dataobj).sum() == data.sum()

    def test_oblique_orientation_is_preserved(self, workspace):
        c, s = np.cos(np.deg2rad(12.0)), np.sin(np.deg2rad(12.0))
        tilt = np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])
        affine = _las_affine((5.0, 5.0, 5.0), rotation=tilt)
        data = np.random.default_rng(2).integers(0, 1000, size=(60, 52, 40))
        in_file = _save(workspace / "ref.nii.gz", data, affine)
        in_img = nib.load(in_file)

        out = _run(in_file)

        assert np.allclose(out.affine[:3, :3], affine[:3, :3])
        i, j, k = _source_index(out, in_img)
        assert np.array_equal(
            np.asanyarray(out.dataobj), data[i : i + 51, j : j + 51, k : k + 40]
        )


@pytest.mark.heavy
@pytest.mark.requires_freesurfer
class TestCropFovSatisfiesReconAll:
    """The reason for the crop: recon-all's motion-correction step conforms
    the input and stops with ``ERROR! FOV=... > 256`` when the conformed field
    of view exceeds 256 mm. The raw large-FOV reference must hit that error
    and the cropped one must pass it."""

    def _motioncor(self, tmp_path, in_file, subject):
        subjects_dir = tmp_path / "subjects"
        subjects_dir.mkdir(exist_ok=True)
        # FS_V8_XOPTS=0 as freesurfer_workflow sets for the classic recon-all
        # (FreeSurfer 8's extra steps otherwise run a CNN on orig.mgz).
        env = dict(os.environ, SUBJECTS_DIR=str(subjects_dir), FS_V8_XOPTS="0")
        result = subprocess.run(
            [
                "recon-all",
                "-s",
                subject,
                "-i",
                in_file,
                "-motioncor",
                "-no-isrunning",
                "-sd",
                str(subjects_dir),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        return result, subjects_dir / subject / "mri" / "orig.mgz"

    def test_cropped_reference_passes_the_fov_check(self, tmp_path, workspace):
        # A 1 mm reference with a 300 x 260 mm plane, as from a large-FOV
        # protocol after robustfov has cut the neck.
        data = np.random.default_rng(3).integers(0, 1000, size=(300, 260, 170))
        in_file = _save(tmp_path / "ref.nii.gz", data, _las_affine((1.0, 1.0, 1.0)))

        raw, _ = self._motioncor(tmp_path, in_file, "raw")
        assert raw.returncode != 0
        assert "ERROR! FOV=" in raw.stdout + raw.stderr

        node = CropFov()
        node.inputs.in_file = in_file
        node.inputs.max_dim = 256
        cropped_file = node.run().outputs.out_file
        assert nib.load(cropped_file).shape == (256, 256, 170)

        cropped, orig = self._motioncor(tmp_path, cropped_file, "cropped")
        assert cropped.returncode == 0, cropped.stdout[-2000:] + cropped.stderr
        assert "ERROR! FOV=" not in cropped.stdout + cropped.stderr
        assert orig.exists()
