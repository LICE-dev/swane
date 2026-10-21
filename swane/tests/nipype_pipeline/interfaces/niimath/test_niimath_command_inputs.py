"""The niimath interfaces that build their ``op_string`` must not keep it.

``ThrROI``, ``SumMultiVols``, ``NiiMathSliceTimer`` and ``NiiMathRobustFov``
compute ``op_string`` (and, for ``SumMultiVols``, ``in_file``) when the command
line is built. Writing them into the inputs for good made the inputs differ
from what the caller set and made ``SumMultiVols`` outputs depend on the
command line having been built: ``_list_outputs`` on a fresh interface failed
because ``in_file`` was still undefined.
"""

import nibabel as nib
import numpy as np
import pytest

from swane.config.config_enums import SliceTiming
from swane.nipype_pipeline.interfaces.niimath import NiiMathRobustFov
from swane.nipype_pipeline.interfaces.niimath.NiiMathSliceTimer import (
    NiiMathSliceTimer,
)
from swane.nipype_pipeline.interfaces.niimath.SumMultiVols import SumMultiVols
from swane.nipype_pipeline.interfaces.niimath.ThrROI import ThrROI


def _series(path, value=1.0, n_slices=4, n_vols=3):
    img = nib.Nifti1Image(
        np.full((2, 2, n_slices, n_vols), value, dtype=np.float32), np.eye(4)
    )
    img.header.set_xyzt_units("mm", "sec")
    nib.save(img, str(path))
    return str(path)


def _thr_roi(tmp_path):
    node = ThrROI()
    node.inputs.in_file = _series(tmp_path / "seg.nii.gz")
    node.inputs.seg_val_min = 10.0
    node.inputs.seg_val_max = 20.0
    return node, "-thr 10.0000000000 -uthr 20.0000000000 -bin"


def _sum_multi_vols(tmp_path):
    files = [_series(tmp_path / ("%s.nii.gz" % n)) for n in "abc"]
    node = SumMultiVols()
    node.inputs.vol_files = files
    node.inputs.out_file = "sum.nii.gz"
    return node, "-add %s -add %s " % (files[1], files[2])


def _slice_timer(tmp_path):
    node = NiiMathSliceTimer()
    node.inputs.in_file = _series(tmp_path / "bold.nii.gz")
    node.inputs.time_repetition = 2.0
    node.inputs.slice_timing = SliceTiming.UP
    return (
        node,
        "-stc --slicetiming 0.000000,0.500000,1.000000,1.500000 -tzero 1.000000",
    )


def _robust_fov(tmp_path):
    node = NiiMathRobustFov()
    node.inputs.in_file = _series(tmp_path / "head.nii.gz")
    node.inputs.brainsize = 120
    node.inputs.out_file = "crop.nii.gz"
    return node, "-robustfov 120"


BUILDERS = [_thr_roi, _sum_multi_vols, _slice_timer, _robust_fov]


@pytest.mark.parametrize("builder", BUILDERS)
class TestCommandBuilding:
    def test_the_command_carries_the_operation(self, tmp_path, builder):
        node, operation = builder(tmp_path)

        assert operation in node.cmdline

    def test_the_inputs_are_left_as_the_caller_set_them(self, tmp_path, builder):
        node, _ = builder(tmp_path)
        values = node.inputs.get()
        hashval = node.inputs.get_hashval()

        node.cmdline

        assert node.inputs.get() == values
        assert node.inputs.get_hashval() == hashval

    def test_building_the_command_twice_gives_the_same_command(self, tmp_path, builder):
        node, _ = builder(tmp_path)

        assert node.cmdline == node.cmdline


class TestSumMultiVolsOutputs:
    """The default output name comes from the first volume, not from a command."""

    def _node(self, tmp_path, out_file=None):
        files = [_series(tmp_path / ("%s.nii.gz" % n)) for n in "abc"]
        node = SumMultiVols()
        node.inputs.vol_files = files
        if out_file:
            node.inputs.out_file = out_file
        return node

    def test_default_name_without_building_the_command(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        node = self._node(tmp_path)

        assert node._list_outputs()["out_file"] == str(tmp_path / "a_maths.nii.gz")

    def test_default_name_after_building_the_command(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        node = self._node(tmp_path)
        node.cmdline

        assert node._list_outputs()["out_file"] == str(tmp_path / "a_maths.nii.gz")

    def test_explicit_name_without_building_the_command(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        node = self._node(tmp_path, out_file="sum.nii.gz")

        assert node._list_outputs()["out_file"] == str(tmp_path / "sum.nii.gz")

    def test_the_command_writes_the_default_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        node = self._node(tmp_path)

        assert node.cmdline.endswith(str(tmp_path / "a_maths.nii.gz"))


def test_real_niimath_sums_the_volumes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    files = [_series(tmp_path / ("v%d.nii.gz" % i), value=i) for i in (1, 2, 4)]
    node = SumMultiVols()
    node.inputs.vol_files = files
    node.inputs.out_file = "sum.nii.gz"

    out = nib.load(node.run().outputs.out_file).get_fdata()

    np.testing.assert_array_equal(out, np.full(out.shape, 7.0))


def test_real_niimath_thresholds_the_segmentation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    labels = np.array([0, 9, 10, 15, 20, 21], dtype=np.float32).reshape(1, 1, 6)
    nib.save(nib.Nifti1Image(labels, np.eye(4)), tmp_path / "seg.nii.gz")
    node = ThrROI()
    node.inputs.in_file = str(tmp_path / "seg.nii.gz")
    node.inputs.seg_val_min = 10.0
    node.inputs.seg_val_max = 20.0
    node.inputs.out_file = "roi.nii.gz"

    out = nib.load(node.run().outputs.out_file).get_fdata().ravel()

    np.testing.assert_array_equal(out, [0, 0, 1, 1, 1, 0])
