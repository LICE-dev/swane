"""Unit tests for
:class:`swane.nipype_pipeline.nodes.AffineToRAS.AffineToRAS`.

The load-bearing behaviour: given the ANTs forward (reference -> moving, ITK/LPS)
transform of the diff -> ref registration, the node must emit the **diffusion-RAS
-> reference-RAS** 4x4 affine as a plain text file (``np.loadtxt``-readable),
because :class:`~swane.nipype_pipeline.nodes.DipyTracking.DipyTracking` feeds it
straight into ``transform_streamlines`` in RASMM space. Getting the direction or
the LPS->RAS handedness wrong silently places every streamline in the wrong
space, so the direction is proven end-to-end here (not merely "a 4x4 comes out").
"""

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.AffineToRAS import AffineToRAS


def _rigid_ras(theta, translation):
    """A known RAS->RAS rigid affine (rotation about z + translation)."""
    matrix = np.eye(4)
    matrix[:3, :3] = np.array(
        [
            [np.cos(theta), -np.sin(theta), 0.0],
            [np.sin(theta), np.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    matrix[:3, 3] = translation
    return matrix


@pytest.fixture
def registration_images(make_nifti):
    """A reference (T1) grid and a differently-oriented moving (diffusion) grid.

    Non-trivial, non-identity affines are used deliberately: a voxel-space or
    FSL-space confusion in the conversion would surface as a wrong RAS matrix.
    """
    ref_affine = np.array(
        [[-1.0, 0, 0, 90], [0, 1.0, 0, -120], [0, 0, 2.0, -60], [0, 0, 0, 1]]
    )
    mov_affine = np.array(
        [[0, -2.5, 0, 40], [-2.5, 0, 0, 50], [0, 0, 2.5, -30], [0, 0, 0, 1]]
    )
    reference = make_nifti("ref.nii.gz", shape=(20, 22, 12), affine=ref_affine)
    moving = make_nifti("mov.nii.gz", shape=(16, 16, 10), affine=mov_affine)
    return reference, moving


class TestAffineToRAS:
    def test_emits_diff_to_ref_ras_affine(
        self, workspace, registration_images, tmp_path
    ):
        """Round-trip: an ITK transform representing ref -> diff (as the ANTs
        forward transform does) must come back out as the diff -> ref RAS affine,
        i.e. the inverse, expressed in RAS."""
        from nitransforms import linear

        reference, moving = registration_images

        # The RAS affine we ultimately want the node to emit (diff -> ref).
        diff2ref = _rigid_ras(0.3, [5.0, -7.0, 3.0])
        # The ANTs forward transform maps reference -> moving in nitransforms'
        # internal RAS convention, i.e. the inverse of diff -> ref.
        ref2diff = np.linalg.inv(diff2ref)

        itk_path = tmp_path / "ants_fwd.txt"
        linear.Affine(ref2diff, reference=nib.load(reference)).to_filename(
            str(itk_path), fmt="itk"
        )

        node = AffineToRAS()
        node.inputs.in_transform = str(itk_path)
        node.inputs.source_file = moving
        node.inputs.reference_file = reference
        node.run()

        out = node._list_outputs()["out_ras"]
        emitted = np.loadtxt(out).reshape(4, 4)
        assert np.allclose(emitted, diff2ref, atol=1e-6)

    def test_accepts_transform_list_and_uses_last(
        self, workspace, registration_images, tmp_path
    ):
        """The ANTs ``fwd_transforms`` output is a list; the node takes the
        affine (last element), exactly like ``AffineToFSL``."""
        from nitransforms import linear

        reference, moving = registration_images
        diff2ref = _rigid_ras(-0.15, [2.0, 4.0, -1.0])
        ref2diff = np.linalg.inv(diff2ref)

        itk_path = tmp_path / "ants_fwd_list.txt"
        linear.Affine(ref2diff, reference=nib.load(reference)).to_filename(
            str(itk_path), fmt="itk"
        )

        node = AffineToRAS()
        node.inputs.in_transform = [str(itk_path)]
        node.inputs.source_file = moving
        node.inputs.reference_file = reference
        node.run()

        emitted = np.loadtxt(node._list_outputs()["out_ras"]).reshape(4, 4)
        assert np.allclose(emitted, diff2ref, atol=1e-6)
