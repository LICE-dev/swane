"""Tests for :func:`swane.nipype_pipeline.interfaces.ants.match_mask_geometry`,
the image/mask geometry guard shared by AntsN4BiasFieldCorrection and
AntsAtropos.

Within tolerance (origin 0.1 mm, spacing 1e-3 mm, direction cosines 1e-3, same
shape) the mask is given the image's exact geometry, as ITK demands agreement to
about 1e-6; beyond it the pair is refused with a message naming what differs.
The previous guard compared origins only: a mask on another grid whose origin
fell within 0.1 mm silently had the image's spacing and direction forced on it,
and one with the same origin reached ITK/Atropos, which failed with an opaque
error.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.interfaces.ants import match_mask_geometry
from swane.nipype_pipeline.interfaces.ants.AntsAtropos import AntsAtropos
from swane.nipype_pipeline.interfaces.ants.AntsN4BiasFieldCorrection import (
    AntsN4BiasFieldCorrection,
)


def _ants_image(
    shape=(6, 6, 6), spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0), direction=None
):
    import ants

    return ants.from_numpy(
        np.ones(shape, dtype=np.float32),
        origin=tuple(origin),
        spacing=tuple(spacing),
        direction=np.eye(3) if direction is None else np.asarray(direction),
    )


class TestMatchMaskGeometry:
    def test_identical_geometry_is_accepted(self):
        img = _ants_image()
        mask = match_mask_geometry(img, _ants_image())
        assert mask.origin == img.origin

    def test_small_origin_offset_is_aligned(self):
        img = _ants_image(origin=(10.0, -5.0, 3.0))
        mask = match_mask_geometry(img, _ants_image(origin=(10.05, -5.0, 3.0)))
        assert mask.origin == img.origin

    def test_float_noise_in_spacing_and_direction_is_aligned(self):
        img = _ants_image()
        noisy_direction = np.eye(3)
        noisy_direction[0, 1] = 1e-5
        mask = match_mask_geometry(
            img,
            _ants_image(spacing=(1.0 + 1e-5, 1.0, 1.0), direction=noisy_direction),
        )
        assert mask.spacing == img.spacing
        assert np.array_equal(mask.direction, img.direction)

    def test_large_origin_offset_is_refused(self):
        with pytest.raises(RuntimeError, match="do not coincide.*origin"):
            match_mask_geometry(_ants_image(), _ants_image(origin=(5.0, 0.0, 0.0)))

    def test_other_spacing_within_the_origin_tolerance_is_refused(self):
        with pytest.raises(RuntimeError, match="do not coincide.*spacing"):
            match_mask_geometry(
                _ants_image(),
                _ants_image(spacing=(2.0, 2.0, 2.0), origin=(0.05, 0.0, 0.0)),
            )

    def test_other_direction_is_refused(self):
        with pytest.raises(RuntimeError, match="do not coincide.*direction"):
            match_mask_geometry(
                _ants_image(), _ants_image(direction=np.diag([1.0, -1.0, 1.0]))
            )

    def test_other_shape_is_refused(self):
        with pytest.raises(RuntimeError, match="do not coincide.*shape"):
            match_mask_geometry(_ants_image(), _ants_image(shape=(6, 6, 5)))


def _write(path, data, affine):
    nib.save(nib.Nifti1Image(data, affine), str(path))
    return os.path.abspath(str(path))


@pytest.fixture
def image_file(workspace):
    """A small LAS image with an intensity ramp, as the nodes see on disk."""
    shape = (24, 24, 24)
    rng = np.random.default_rng(0)
    data = 100 + np.indices(shape).sum(0) * 3.0 + rng.random(shape) * 10
    data[:4] = 0
    data[-4:] = 0
    affine = np.diag([-1.0, 1.0, 1.0, 1.0])
    affine[:3, 3] = [10.0, -5.0, 3.0]
    return _write(workspace / "img.nii.gz", data.astype(np.float32), affine), affine


def _mask_file(workspace, affine, shape=(24, 24, 24)):
    mask = np.zeros(shape, dtype=np.uint8)
    mask[4:-4, 4:-4, 4:-4] = 1
    return _write(workspace / "mask.nii.gz", mask, affine)


def _node(iface, image, mask):
    node = iface()
    node.inputs.in_file = image
    node.inputs.mask_file = mask
    node.inputs.num_threads = 1
    if iface is AntsN4BiasFieldCorrection:
        node.inputs.out_file = os.path.abspath("n4.nii.gz")
    else:
        node.inputs.iterations = 2
    return node


@pytest.mark.parametrize(
    "iface", [AntsN4BiasFieldCorrection, AntsAtropos], ids=["n4", "atropos"]
)
class TestNodesUseTheGuard:
    """Real antspyx runs: the guard sits in front of N4 and Atropos alike."""

    def test_small_origin_offset_runs(self, iface, workspace, image_file):
        image, affine = image_file
        shifted = affine.copy()
        shifted[0, 3] += 0.05
        _node(iface, image, _mask_file(workspace, shifted)).run()

    def test_other_spacing_within_origin_tolerance_is_refused(
        self, iface, workspace, image_file
    ):
        image, affine = image_file
        coarse = affine.copy()
        coarse[:3, :3] *= 2.0
        coarse[0, 3] += 0.05
        with pytest.raises(Exception, match="do not coincide.*spacing"):
            _node(iface, image, _mask_file(workspace, coarse)).run()

    def test_other_direction_is_refused_clearly(self, iface, workspace, image_file):
        image, affine = image_file
        flipped = affine.copy()
        flipped[:3, :3] = np.diag([1.0, -1.0, 1.0]) @ flipped[:3, :3]
        with pytest.raises(Exception, match="do not coincide.*direction"):
            _node(iface, image, _mask_file(workspace, flipped)).run()

    def test_other_shape_is_refused(self, iface, workspace, image_file):
        image, affine = image_file
        with pytest.raises(Exception, match="do not coincide.*shape"):
            _node(iface, image, _mask_file(workspace, affine, shape=(24, 24, 20))).run()
