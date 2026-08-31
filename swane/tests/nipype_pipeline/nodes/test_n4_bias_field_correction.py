"""Unit tests for
:class:`swane.nipype_pipeline.nodes.N4BiasFieldCorrection.N4BiasFieldCorrection`.

The node wraps ``ants.n4_bias_field_correction`` (never SimpleITK, never the
ANTs binaries). The tests below fake only ``ants.n4_bias_field_correction``
itself -- image reading/writing and the mask-selection logic stay real -- so
the parts that carry scientific meaning are exercised for real:

* which mask ends up in front of N4 (explicit ``mask_file``, the
  ``skull_stripped`` fallback, or the automatic Otsu fallback);
* the geometrical-coherence guard between image and mask;
* the ``max_iterations`` -> ``convergence`` translation, which must always
  carry a ``tol`` key (antspyx indexes it unconditionally).
"""

import os

import numpy as np
import nibabel as nib
import pytest
from nipype.interfaces.base import isdefined

from swane.nipype_pipeline.nodes.N4BiasFieldCorrection import (
    N4BiasFieldCorrection,
    N4_DEFAULT_TOL,
)


def _fake_n4(created):
    """Stand-in for ``ants.n4_bias_field_correction`` that records its inputs
    and returns the image unchanged, so the node's ``image_write`` step still
    has something real to write."""

    def _fake(image, mask=None, **kwargs):
        created["image"] = image
        created["mask"] = mask
        created["kwargs"] = dict(kwargs)
        return image.clone()

    return _fake


def _run(node, monkeypatch):
    import ants

    created = {}
    monkeypatch.setattr(ants, "n4_bias_field_correction", _fake_n4(created))
    node.run()
    return created


class TestN4BiasFieldCorrectionSpec:
    def test_skull_stripped_defaults_false(self):
        node = N4BiasFieldCorrection()
        assert node.inputs.skull_stripped is False

    def test_mask_file_optional_and_undefined_by_default(self):
        node = N4BiasFieldCorrection()
        assert not isdefined(node.inputs.mask_file)

    def test_max_iterations_optional_and_undefined_by_default(self):
        node = N4BiasFieldCorrection()
        assert not isdefined(node.inputs.max_iterations)

    def test_output_declared(self):
        out = N4BiasFieldCorrection().output_spec().get()
        assert "out_file" in out


class TestN4BiasFieldCorrectionMaskSelection:
    def test_explicit_mask_is_binarized(self, workspace, make_nifti, monkeypatch):
        """A non-binary mask (e.g. multi-label) must collapse to 0/1."""
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("img.nii.gz", shape=(6, 6, 6))
        node.inputs.mask_file = make_nifti(
            "mask.nii.gz",
            data=np.array([[[0, 2], [0, 3]], [[0, 0], [1, 0]]], dtype=np.float32),
        )
        created = _run(node, monkeypatch)
        assert set(np.unique(created["mask"].numpy())) <= {0.0, 1.0}
        assert created["mask"].numpy()[0, 0, 1] == 1.0
        assert created["mask"].numpy()[0, 0, 0] == 0.0

    def test_skull_stripped_uses_nonzero_voxels(
        self, workspace, make_nifti, monkeypatch
    ):
        node = N4BiasFieldCorrection()
        data = np.zeros((4, 4, 4), dtype=np.float32)
        data[1, 1, 1] = 5.0
        node.inputs.in_file = make_nifti("img.nii.gz", data=data)
        node.inputs.skull_stripped = True
        created = _run(node, monkeypatch)
        assert created["mask"].numpy()[1, 1, 1] == 1.0
        assert created["mask"].numpy().sum() == 1.0

    def test_default_fallback_uses_otsu_segmentation(
        self, workspace, make_nifti, monkeypatch
    ):
        """Neither a mask nor skull_stripped: automatic Otsu thresholding."""
        import ants

        node = N4BiasFieldCorrection()
        data = np.zeros((6, 6, 6), dtype=np.float32)
        data[2:4, 2:4, 2:4] = 100.0
        node.inputs.in_file = make_nifti("img.nii.gz", data=data)

        otsu_calls = {}
        real_otsu = ants.otsu_segmentation

        def _spy_otsu(image, k=1, **kwargs):
            otsu_calls["k"] = k
            return real_otsu(image, k=k, **kwargs)

        monkeypatch.setattr(ants, "otsu_segmentation", _spy_otsu)
        created = _run(node, monkeypatch)

        assert otsu_calls["k"] == 1
        assert set(np.unique(created["mask"].numpy())) <= {0.0, 1.0}


class TestN4BiasFieldCorrectionGeometryGuard:
    def test_small_origin_mismatch_is_forced_to_match(
        self, workspace, make_nifti, monkeypatch
    ):
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("img.nii.gz", shape=(6, 6, 6))
        mismatched_affine = np.eye(4)
        mismatched_affine[0, 3] = 0.05  # within the 0.1mm tolerance
        node.inputs.mask_file = make_nifti(
            "mask.nii.gz", shape=(6, 6, 6), affine=mismatched_affine
        )
        created = _run(node, monkeypatch)
        assert created["mask"].origin == created["image"].origin

    def test_large_origin_mismatch_raises(self, workspace, make_nifti, monkeypatch):
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("img.nii.gz", shape=(6, 6, 6))
        mismatched_affine = np.eye(4)
        mismatched_affine[0, 3] = 5.0  # well past the 0.1mm tolerance
        node.inputs.mask_file = make_nifti(
            "mask.nii.gz", shape=(6, 6, 6), affine=mismatched_affine
        )
        with pytest.raises(Exception, match="do not coincide"):
            node.run()


class TestN4BiasFieldCorrectionRuntime:
    def test_max_iterations_becomes_convergence_with_default_tol(
        self, workspace, make_nifti, monkeypatch
    ):
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("img.nii.gz", shape=(6, 6, 6))
        node.inputs.skull_stripped = True
        node.inputs.max_iterations = [30, 20, 10, 5]
        created = _run(node, monkeypatch)
        assert created["kwargs"]["convergence"] == {
            "iters": [30, 20, 10, 5],
            "tol": N4_DEFAULT_TOL,
        }

    def test_no_convergence_kwarg_when_max_iterations_unset(
        self, workspace, make_nifti, monkeypatch
    ):
        """Leaving max_iterations alone must keep antspyx's own defaults."""
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("img.nii.gz", shape=(6, 6, 6))
        node.inputs.skull_stripped = True
        created = _run(node, monkeypatch)
        assert "convergence" not in created["kwargs"]

    def test_num_threads_is_exported_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        var = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"
        monkeypatch.delenv(var, raising=False)
        seen = {}

        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("img.nii.gz", shape=(6, 6, 6))
        node.inputs.skull_stripped = True
        node.inputs.num_threads = 3

        import ants

        real_fake = _fake_n4({})

        def _spy(*args, **kwargs):
            seen["threads"] = os.environ.get(var)
            return real_fake(*args, **kwargs)

        monkeypatch.setattr(ants, "n4_bias_field_correction", _spy)
        node.run()

        assert seen["threads"] == "3"
        assert var not in os.environ

    def test_default_out_file_name(self, workspace, make_nifti, monkeypatch):
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(6, 6, 6))
        node.inputs.skull_stripped = True
        _run(node, monkeypatch)
        outputs = node._list_outputs()
        assert outputs["out_file"] == os.path.abspath("unbiased_t1.nii.gz")
        assert os.path.exists(outputs["out_file"])

    def test_custom_out_file_name(self, workspace, make_nifti, monkeypatch):
        node = N4BiasFieldCorrection()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(6, 6, 6))
        node.inputs.out_file = "corrected.nii.gz"
        node.inputs.skull_stripped = True
        _run(node, monkeypatch)
        outputs = node._list_outputs()
        assert outputs["out_file"] == os.path.abspath("corrected.nii.gz")
        assert os.path.exists(outputs["out_file"])


@pytest.mark.heavy
class TestN4BiasFieldCorrectionRealRun:
    """A real (tiny) antspyx N4 correction; opt-in via ``--run-heavy``."""

    def test_reduces_a_synthetic_bias_field(self, workspace, make_nifti):
        shape = (24, 24, 24)
        base = np.zeros(shape, dtype=np.float32)
        base[6:18, 6:18, 6:18] = 100.0
        # a smooth multiplicative bias ramp along x
        ramp = np.linspace(0.6, 1.4, shape[0]).astype(np.float32)
        biased = base * ramp[:, None, None]

        in_file = make_nifti("biased.nii.gz", data=biased)
        node = N4BiasFieldCorrection()
        node.inputs.in_file = in_file
        node.inputs.skull_stripped = True
        node.run()
        outputs = node._list_outputs()

        corrected = nib.load(outputs["out_file"]).get_fdata()
        assert np.all(np.isfinite(corrected))
        assert corrected.shape == shape
        # the corrected foreground should be more uniform than the biased input
        fg = base > 0
        assert corrected[fg].std() < biased[fg].std()
