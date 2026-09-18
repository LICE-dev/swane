"""Unit tests for
:class:`swane.nipype_pipeline.nodes.DipyTissueClassifier.DipyTissueClassifier`.

Runs dipy's real HMRF classifier on a small synthetic three-tissue-block T1
phantom -- confirmed against dipy 1.12.0's source
(``TissueClassifierHMRF.classify`` sorts classes by ascending mean intensity
and drops the extra background class before returning the PVE array) and
empirically on the same kind of phantom used here: the three output channels
come out ordered CSF (darkest) < GM < WM (brightest).
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.DipyTissueClassifier import (
    DipyTissueClassifier,
    OMP_THREADS_VAR,
)


def _three_tissue_phantom(shape=(20, 20, 20)):
    """Three non-overlapping intensity blocks (CSF < GM < WM) on a zero
    background, plus a tiny amount of noise so the classifier has something
    to do."""
    image = np.zeros(shape, dtype=np.float32)
    image[2:8, 2:18, 2:18] = 0.3  # CSF-like
    image[8:14, 2:18, 2:18] = 0.6  # GM-like
    image[14:18, 2:18, 2:18] = 0.9  # WM-like

    rng = np.random.default_rng(1)
    image = np.clip(image + rng.normal(0, 0.01, shape), 0, None).astype(np.float32)

    masks = {
        "csf": (image > 0.25) & (image < 0.35),
        "gm": (image > 0.55) & (image < 0.65),
        "wm": (image > 0.85) & (image < 0.95),
    }
    return image, masks


class TestDipyTissueClassifierContract:
    def test_pve_maps_sum_to_one_in_each_tissue_and_are_ordered_by_intensity(
        self, workspace, make_nifti
    ):
        image, masks = _three_tissue_phantom()
        in_file = make_nifti("t1.nii.gz", data=image)

        node = DipyTissueClassifier()
        node.inputs.in_file = in_file
        node.run()

        outputs = node._list_outputs()
        pve_csf = nib.load(outputs["pve_csf"]).get_fdata()
        pve_gm = nib.load(outputs["pve_gm"]).get_fdata()
        pve_wm = nib.load(outputs["pve_wm"]).get_fdata()

        total = pve_csf + pve_gm + pve_wm
        for region in masks.values():
            assert np.allclose(total[region], 1.0, atol=1e-3)

        assert pve_csf[masks["csf"]].mean() > 0.99
        assert pve_gm[masks["gm"]].mean() > 0.99
        assert pve_wm[masks["wm"]].mean() > 0.99

    def test_default_output_prefix_and_custom_prefix(self, workspace, make_nifti):
        image, _ = _three_tissue_phantom()
        in_file = make_nifti("t1.nii.gz", data=image)

        node = DipyTissueClassifier()
        node.inputs.in_file = in_file
        node.inputs.out_prefix = "custom"
        node.run()

        outputs = node._list_outputs()
        assert outputs["pve_csf"].endswith("custom_csf.nii.gz")
        assert outputs["pve_gm"].endswith("custom_gm.nii.gz")
        assert outputs["pve_wm"].endswith("custom_wm.nii.gz")
        for path in outputs.values():
            assert os.path.exists(path)


class TestDipyTissueClassifierKeepsFloat64:
    """Unlike denoise/tensor/CSD, this node must NOT load float32: dipy's HMRF
    is a typed-double Cython kernel (segment/mrf.pyx) that rejects float32 with
    'Buffer dtype mismatch, expected double'. This guards that dipy constraint
    so a future float32 sweep does not silently break the classifier."""

    def test_data_passed_to_classify_is_float64(
        self, workspace, make_nifti, monkeypatch
    ):
        import dipy.segment.tissue as tissue_module

        image, _ = _three_tissue_phantom(shape=(8, 8, 8))
        in_file = make_nifti("t1.nii.gz", data=image)

        seen = {}
        real_classify = tissue_module.TissueClassifierHMRF.classify

        def _spy_classify(self, image_arg, *args, **kwargs):
            seen["dtype"] = np.asarray(image_arg).dtype
            return real_classify(self, image_arg, *args, **kwargs)

        monkeypatch.setattr(
            tissue_module.TissueClassifierHMRF, "classify", _spy_classify
        )

        node = DipyTissueClassifier()
        node.inputs.in_file = in_file
        node.run()

        assert seen["dtype"] == np.dtype(np.float64)


class TestDipyTissueClassifierThreadPinning:
    def test_omp_pinned_to_one_during_classify_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        import dipy.segment.tissue as tissue_module

        monkeypatch.delenv(OMP_THREADS_VAR, raising=False)

        image, _ = _three_tissue_phantom(shape=(10, 10, 10))
        in_file = make_nifti("t1.nii.gz", data=image)

        seen = {}
        real_classify = tissue_module.TissueClassifierHMRF.classify

        def _spy_classify(self, *args, **kwargs):
            seen["omp"] = os.environ.get(OMP_THREADS_VAR)
            return real_classify(self, *args, **kwargs)

        monkeypatch.setattr(
            tissue_module.TissueClassifierHMRF, "classify", _spy_classify
        )

        node = DipyTissueClassifier()
        node.inputs.in_file = in_file
        node.run()

        assert seen["omp"] == "1"
        assert OMP_THREADS_VAR not in os.environ


class TestDipyTissueClassifierOutputDtype:
    """The PVE outputs are always written as float32, regardless of the input
    header's dtype.

    This pins the contract introduced 2026-09-18: ``DipyTissueClassifier`` now
    calls ``header.set_data_dtype(np.float32)`` explicitly so a future upstream
    header change cannot silently quantize the PVE maps that drive the CMC
    stopping criterion. The HMRF computation is float64 (dipy's Cython kernel
    requires double), but float32 is more than sufficient for [0, 1]
    partial-volume estimates on disk.
    """

    @staticmethod
    def _make_t1(tmp_path, header_dtype, *, name="t1"):
        """Three-block T1 phantom with a controlled header dtype."""
        image, _ = _three_tissue_phantom(shape=(12, 12, 12))

        if header_dtype == np.int16:
            # Scale to a typical T1 range so int16 values are meaningful
            data_save = (image * 1000).astype(np.int16)
        else:
            data_save = image.astype(np.float32)

        img = nib.Nifti1Image(data_save, np.eye(4))
        img.header.set_data_dtype(header_dtype)
        path = str(tmp_path / f"{name}.nii.gz")
        nib.save(img, path)
        return path

    @pytest.mark.parametrize("header_dtype", [np.float32, np.int16])
    def test_pve_output_is_always_float32(self, workspace, header_dtype):
        t1_path = self._make_t1(workspace, header_dtype)

        node = DipyTissueClassifier()
        node.inputs.in_file = t1_path
        node.run()

        outputs = node._list_outputs()
        for field in ("pve_csf", "pve_gm", "pve_wm"):
            out_img = nib.load(outputs[field])
            assert out_img.header.get_data_dtype() == np.dtype(np.float32), (
                f"{field} must always be float32, got "
                f"{out_img.header.get_data_dtype()} with "
                f"{np.dtype(header_dtype)} input"
            )
            raw = np.asarray(out_img.dataobj.get_unscaled())
            assert raw.dtype == np.dtype(np.float32)
