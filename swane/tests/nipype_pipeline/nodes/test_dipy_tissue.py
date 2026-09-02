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
