"""Unit tests for
:class:`swane.nipype_pipeline.interfaces.ants.AntsAtropos.AntsAtropos`.

The node wraps ``ants.atropos`` (antspyx, never the ANTs binary). The fast
tests fake only ``ants.atropos`` -- image read/write and mask selection stay
real -- so the meaningful parts are exercised: the ``i``/``m``/``c`` parameter
strings, the mask fallback, and the posterior ordering/paths.
"""

import os

import numpy as np
import nibabel as nib
import pytest
from nipype.interfaces.base import isdefined

from swane.nipype_pipeline.interfaces.ants.AntsAtropos import AntsAtropos


def _fake_atropos(created):
    def _fake(a, x, i="Kmeans[3]", m=None, c=None, **kwargs):
        created["a"] = a
        created["x"] = x
        created["i"] = i
        created["m"] = m
        created["c"] = c
        created["kwargs"] = dict(kwargs)
        return {
            "segmentation": a.clone(),
            "probabilityimages": [a.clone(), a.clone(), a.clone()],
        }

    return _fake


def _run(node, monkeypatch):
    import ants

    created = {}
    monkeypatch.setattr(ants, "atropos", _fake_atropos(created))
    node.run()
    return created


class TestAntsAtroposSpec:
    def test_defaults(self):
        node = AntsAtropos()
        assert node.inputs.number_classes == 3
        assert node.inputs.mrf_smoothing == 0.0
        assert node.inputs.mrf_radius == 1
        assert node.inputs.iterations == 10
        assert not isdefined(node.inputs.mask_file)

    def test_outputs_declared(self):
        out = AntsAtropos().output_spec().get()
        assert "partial_volume_files" in out
        assert "tissue_class_map" in out


class TestAntsAtroposParams:
    def test_param_strings_from_defaults(self, workspace, make_nifti, monkeypatch):
        node = AntsAtropos()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(6, 6, 6))
        created = _run(node, monkeypatch)
        assert created["i"] == "Kmeans[3]"
        assert created["m"] == "[0,1x1x1]"
        assert created["c"] == "[10,0]"

    def test_param_strings_reflect_traits(self, workspace, make_nifti, monkeypatch):
        node = AntsAtropos()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(6, 6, 6))
        node.inputs.mrf_smoothing = 0.1
        node.inputs.mrf_radius = 2
        node.inputs.iterations = 3
        created = _run(node, monkeypatch)
        assert created["i"] == "Kmeans[3]"
        assert created["m"] == "[0.1,2x2x2]"
        assert created["c"] == "[3,0]"


class TestAntsAtroposMask:
    def test_default_mask_is_nonzero_voxels(self, workspace, make_nifti, monkeypatch):
        node = AntsAtropos()
        data = np.zeros((4, 4, 4), dtype=np.float32)
        data[1, 1, 1] = 5.0
        node.inputs.in_file = make_nifti("t1.nii.gz", data=data)
        created = _run(node, monkeypatch)
        assert created["x"].numpy()[1, 1, 1] == 1.0
        assert created["x"].numpy().sum() == 1.0

    def test_explicit_mask_is_binarized(self, workspace, make_nifti, monkeypatch):
        node = AntsAtropos()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(2, 2, 2))
        node.inputs.mask_file = make_nifti(
            "mask.nii.gz",
            data=np.array([[[0, 2], [0, 3]], [[0, 0], [1, 0]]], dtype=np.float32),
        )
        created = _run(node, monkeypatch)
        assert set(np.unique(created["x"].numpy())) <= {0.0, 1.0}


class TestAntsAtroposOutputs:
    def test_three_posteriors_and_seg_written(self, workspace, make_nifti, monkeypatch):
        node = AntsAtropos()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(6, 6, 6))
        _run(node, monkeypatch)
        outputs = node._list_outputs()
        assert len(outputs["partial_volume_files"]) == 3
        for p in outputs["partial_volume_files"]:
            assert os.path.exists(p)
        assert os.path.exists(outputs["tissue_class_map"])

    def test_num_threads_exported_then_restored(
        self, workspace, make_nifti, monkeypatch
    ):
        var = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"
        monkeypatch.delenv(var, raising=False)
        seen = {}
        node = AntsAtropos()
        node.inputs.in_file = make_nifti("t1.nii.gz", shape=(6, 6, 6))
        node.inputs.num_threads = 3
        import ants

        def _spy(a, x, i=None, m=None, c=None, **kwargs):
            seen["threads"] = os.environ.get(var)
            return {
                "segmentation": a.clone(),
                "probabilityimages": [a.clone(), a.clone(), a.clone()],
            }

        monkeypatch.setattr(ants, "atropos", _spy)
        node.run()
        assert seen["threads"] == "3"
        assert var not in os.environ


@pytest.mark.heavy
class TestAntsAtroposRealRun:
    """A real (tiny) antspyx Atropos run; opt-in via ``--run-heavy``. Confirms
    the documented ascending-intensity class ordering (CSF<GM<WM)."""

    def test_posteriors_ordered_by_ascending_intensity(self, workspace, make_nifti):
        shape = (24, 24, 24)
        data = np.zeros(shape, dtype=np.float32)
        data[:, :, 4:10] = 30.0  # "CSF" plateau (lowest)
        data[:, :, 10:16] = 90.0  # "GM"  plateau
        data[:, :, 16:22] = 160.0  # "WM"  plateau (highest)
        # Give each plateau a tiny within-class variance. Atropos fits a Gaussian
        # mixture; perfectly constant plateaus make the per-class covariance
        # singular (ITK raises "Covariance is singular (determinant = 0)") and the
        # run aborts before producing any posteriors. Real tissue always has some
        # variance, so a fixed-seed jitter keeps the phantom realistic while still
        # letting the ascending-intensity ordering be asserted below.
        rng = np.random.default_rng(0)
        data = data + rng.normal(0.0, 3.0, shape).astype(np.float32)
        node = AntsAtropos()
        node.inputs.in_file = make_nifti("phantom.nii.gz", data=data)
        node.run()
        outputs = node._list_outputs()
        posteriors = [nib.load(p).get_fdata() for p in outputs["partial_volume_files"]]
        # class k should peak on the k-th intensity plateau (ascending order)
        plateaus = [(4, 10), (10, 16), (16, 22)]
        for k, (lo, hi) in enumerate(plateaus):
            in_plateau = posteriors[k][:, :, lo:hi].mean()
            others = np.mean(
                [
                    posteriors[k][:, :, l:h].mean()
                    for j, (l, h) in enumerate(plateaus)
                    if j != k
                ]
            )
            assert in_plateau > others
