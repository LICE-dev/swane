"""Unit tests for :class:`swane.nipype_pipeline.interfaces.geometry.ForceOrient.ForceOrient`.

Reorientation is done with ``nibabel`` (``as_reoriented`` to the LAS layout, the
radiological RL/PA/IS convention), so both the output-name helper and the actual
reorientation are exercised here without FSL.
"""

import os

import numpy as np
import nibabel as nib
import pytest
from nipype.interfaces.base import isdefined

from swane.nipype_pipeline.interfaces.geometry.ForceOrient import ForceOrient


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


# x-axis flip of the FSL b-vector convention.
_FLIP_X = np.diag([-1.0, 1.0, 1.0])


def _rotation_x(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _fsl_frame(affine):
    """FSL-convention b-vector -> world direction for ``affine``.

    FSL b-vectors lie along the voxel axes, with x mirrored when the
    voxel-to-world determinant is positive. Written out independently of the
    interface's own implementation.
    """
    axes = affine[:3, :3] / np.linalg.norm(affine[:3, :3], axis=0)
    return axes @ _FLIP_X if np.linalg.det(axes) > 0 else axes


def _affine(axes, zooms=(2.0, 2.5, 3.0)):
    affine = np.eye(4)
    affine[:3, :3] = np.asarray(axes, dtype=float) @ np.diag(zooms)
    affine[:3, 3] = [30.0, -20.0, 10.0]
    return affine


# World (RAS) gradient directions, a b0 first.
_GRADIENTS = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.6, 0.48, 0.64],
        [-0.36, 0.8, -0.48],
    ]
)


class TestForceOrientBvecs:
    """ForceOrient permutes/flips the voxel axes; FSL b-vectors are expressed
    along those axes, so they must follow the same permutation/flip or every
    tensor, fibre orientation and tract computed downstream is rotated (90
    degrees for a sagittal or coronal DWI). The physical gradient each b-vector
    stands for must be the same before and after the reorientation.
    """

    def _run(self, workspace, affine, bvecs=None, shape=(5, 6, 7, 6)):
        # Inputs in their own folder, as dcm2niix's node directory is: the
        # outputs go to the working directory (the node's own).
        in_dir = workspace / "inputs"
        in_dir.mkdir(exist_ok=True)
        data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
        in_file = os.path.join(str(in_dir), "dwi.nii.gz")
        nib.save(nib.Nifti1Image(data, affine), in_file)
        node = ForceOrient()
        node.inputs.in_file = in_file
        if bvecs is not None:
            in_bvec = os.path.join(str(in_dir), "dwi.bvec")
            np.savetxt(in_bvec, np.asarray(bvecs).T, fmt="%.6f")
            node.inputs.in_bvec = in_bvec
        return node, node.run()

    def test_without_bvec_no_bvec_output(self, workspace):
        _, result = self._run(workspace, _affine(np.eye(3)))
        assert not isdefined(result.outputs.out_bvec)
        assert not os.path.exists(os.path.join(str(workspace), "dwi.bvec"))

    def test_las_input_keeps_the_bvec_file_unchanged(self, workspace):
        """An image already LAS is not touched, nor are its b-vectors."""
        axes = _rotation_x(np.deg2rad(20.0)) @ _FLIP_X  # oblique axial LAS
        bvecs = _GRADIENTS @ _fsl_frame(_affine(axes))
        node, result = self._run(workspace, _affine(axes), bvecs)
        assert result.outputs.out_bvec == os.path.join(str(workspace), "dwi.bvec")
        with open(node.inputs.in_bvec, "rb") as src, open(
            result.outputs.out_bvec, "rb"
        ) as dst:
            assert src.read() == dst.read()

    @pytest.mark.parametrize(
        "axes",
        [
            pytest.param(np.eye(3), id="axial-RAS"),
            pytest.param(np.diag([-1.0, -1.0, 1.0]), id="axial-LPS"),
            pytest.param(np.diag([-1.0, 1.0, -1.0]), id="axial-LAI"),
            pytest.param(
                [[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]],
                id="sagittal-PIR",
            ),
            pytest.param(
                [[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                id="sagittal-PSL",
            ),
            pytest.param(
                [[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]],
                id="coronal-LIA",
            ),
            pytest.param(
                _rotation_x(np.deg2rad(15.0))
                @ np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]]),
                id="oblique-sagittal",
            ),
        ],
    )
    def test_bvecs_keep_their_physical_direction(self, workspace, axes):
        in_affine = _affine(axes)
        bvecs = _GRADIENTS @ _fsl_frame(in_affine)  # rows of W_in^T g
        _, result = self._run(workspace, in_affine, bvecs)

        out_affine = nib.load(result.outputs.out_file).affine
        assert nib.aff2axcodes(out_affine) == ("L", "A", "S")
        out_bvecs = np.loadtxt(result.outputs.out_bvec).T
        assert out_bvecs.shape == bvecs.shape
        # Each b-vector, taken back to world through the LAS frame, is the
        # same physical gradient as before.
        assert np.allclose(out_bvecs @ _fsl_frame(out_affine).T, _GRADIENTS, atol=1e-6)
        # A pure axis permutation/flip: the values are moved and negated, never
        # interpolated, so the b0 stays exactly zero.
        assert np.array_equal(out_bvecs[0], np.zeros(3))
        assert np.allclose(
            np.sort(np.abs(out_bvecs), axis=1), np.sort(np.abs(bvecs), axis=1)
        )


@pytest.mark.requires_dcm2niix
class TestForceOrientBvecsAfterDcm2niix:
    """End to end with the real converter: synthetic DICOM DWI series in the
    standard axial, sagittal and coronal orientations (and the RAS grid of the
    prerelease phantom), with known gradients, through the workflow's own
    dcm2niix settings and ForceOrient. The b-vectors of the LAS output must
    point along the gradients written in the DICOM."""

    @pytest.mark.parametrize(
        "axes",
        [
            pytest.param([[-1, 0, 0], [0, -1, 0], [0, 0, 1]], id="axial-standard"),
            pytest.param([[1, 0, 0], [0, 1, 0], [0, 0, 1]], id="axial-RAS-grid"),
            pytest.param([[0, 0, 1], [-1, 0, 0], [0, -1, 0]], id="sagittal"),
            pytest.param([[-1, 0, 0], [0, 0, 1], [0, -1, 0]], id="coronal"),
        ],
    )
    def test_las_bvecs_match_the_dicom_gradients(self, workspace, axes):
        from swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix import (
            CustomDcm2niix,
        )
        from swane.tests.helpers.phantom.dicom_writer import write_volume_series

        affine = _affine(axes, zooms=(2.0, 2.0, 2.0))
        bvals = [0, 1000, 1000, 1000, 1000, 1000]
        data = np.random.default_rng(0).integers(100, 200, size=(14, 14, 12, 6))
        dicom_dir = os.path.join(str(workspace), "dicom")
        write_volume_series(
            dicom_dir, data.astype(float), affine, bvals=bvals, bvecs=_GRADIENTS
        )

        # dcm2niix writes into its own folder, as in its workflow node.
        conversion_dir = workspace / "conversion"
        conversion_dir.mkdir()
        conversion = CustomDcm2niix()
        conversion.inputs.source_dir = dicom_dir
        conversion.inputs.output_dir = str(conversion_dir)
        conversion.inputs.out_filename = "dti"
        conversion.inputs.bids_format = False
        conversion.inputs.request_dti = True
        conversion.inputs.name_conflicts = 1
        conversion.inputs.merge_imgs = 2
        converted = conversion.run().outputs

        reorient = ForceOrient()
        reorient.inputs.in_file = converted.converted_files
        reorient.inputs.in_bvec = converted.bvecs
        result = reorient.run().outputs

        out_affine = nib.load(result.out_file).affine
        out_bvecs = np.loadtxt(result.out_bvec).T
        world = out_bvecs @ _fsl_frame(out_affine).T
        assert np.allclose(world, _GRADIENTS, atol=1e-4)
