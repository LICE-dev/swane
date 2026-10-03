"""Tests for :class:`swane.nipype_pipeline.interfaces.niimath.NiiMathSliceTimer`.

The slice acquisition times and the ``op_string`` are pure Python and checked
without running niimath. A last test runs the real niimath binary (a pip
dependency of SWANe) on a synthetic series whose slices are sinusoids sampled
at their own acquisition times: after correction every slice must match the
sinusoid sampled at the middle of the TR. This is software regression evidence
only, not scientific validation.
"""

import nibabel as nib
import numpy as np
import pytest
from nipype.interfaces.base import traits

from swane.config.config_enums import SliceTiming
from swane.nipype_pipeline.interfaces.niimath import NiiMathSliceTimer


def _save_series(path, n_slices=4, n_vols=3, data=None):
    if data is None:
        data = np.zeros((2, 2, n_slices, n_vols), dtype=np.float32)
    img = nib.Nifti1Image(data.astype(np.float32), np.eye(4))
    # niimath -stc refuses headers without a time unit; dcm2niix writes seconds.
    img.header.set_xyzt_units("mm", "sec")
    img.header["pixdim"][4] = 2.0
    nib.save(img, str(path))
    return str(path)


class TestSliceTimes:
    """Acquisition time of each slice along the third voxel axis."""

    def test_up_odd(self):
        times = NiiMathSliceTimer.slice_times(5, 2.5, SliceTiming.UP)
        assert times == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])

    def test_up_even(self):
        times = NiiMathSliceTimer.slice_times(4, 2.0, SliceTiming.UP)
        assert times == pytest.approx([0.0, 0.5, 1.0, 1.5])

    def test_down_odd(self):
        times = NiiMathSliceTimer.slice_times(5, 2.5, SliceTiming.DOWN)
        assert times == pytest.approx([2.0, 1.5, 1.0, 0.5, 0.0])

    def test_down_even(self):
        times = NiiMathSliceTimer.slice_times(4, 2.0, SliceTiming.DOWN)
        assert times == pytest.approx([1.5, 1.0, 0.5, 0.0])

    def test_interleaved_odd(self):
        # acquisition order 0, 2, 4, 1, 3
        times = NiiMathSliceTimer.slice_times(5, 2.5, SliceTiming.INTERLEAVED)
        assert times == pytest.approx([0.0, 1.5, 0.5, 2.0, 1.0])

    def test_interleaved_even(self):
        # acquisition order 0, 2, 1, 3
        times = NiiMathSliceTimer.slice_times(4, 2.0, SliceTiming.INTERLEAVED)
        assert times == pytest.approx([0.0, 1.0, 0.5, 1.5])

    def test_unknown_rejected(self):
        with pytest.raises(ValueError):
            NiiMathSliceTimer.slice_times(4, 2.0, SliceTiming.UNKNOWN)


class TestInputs:
    def test_unknown_rejected_by_trait(self):
        node = NiiMathSliceTimer()
        with pytest.raises(traits.TraitError):
            node.inputs.slice_timing = SliceTiming.UNKNOWN

    def test_known_values_accepted(self):
        node = NiiMathSliceTimer()
        for value in (SliceTiming.UP, SliceTiming.DOWN, SliceTiming.INTERLEAVED):
            node.inputs.slice_timing = value
            assert node.inputs.slice_timing == value


class TestCmdline:
    def test_cmdline_has_stc_and_tzero_at_half_tr(self, tmp_path):
        node = NiiMathSliceTimer()
        node.inputs.in_file = _save_series(tmp_path / "bold.nii.gz")
        node.inputs.time_repetition = 2.0
        node.inputs.slice_timing = SliceTiming.UP
        cmd = node.cmdline
        assert "-stc --slicetiming 0.000000,0.500000,1.000000,1.500000" in cmd
        assert " -tzero 1.000000 " in cmd

    def test_cmdline_interleaved_times(self, tmp_path):
        node = NiiMathSliceTimer()
        node.inputs.in_file = _save_series(tmp_path / "bold.nii.gz", n_slices=5)
        node.inputs.time_repetition = 2.5
        node.inputs.slice_timing = SliceTiming.INTERLEAVED
        node._parse_inputs()
        assert node.inputs.op_string == (
            "-stc --slicetiming 0.000000,1.500000,0.500000,2.000000,1.000000"
            " -tzero 1.250000"
        )


def test_real_execution_aligns_slices_to_half_tr(tmp_path, monkeypatch):
    """Slices are sinusoids sampled at their acquisition times; after the
    correction they must equal the sinusoid sampled at TR/2."""
    monkeypatch.chdir(tmp_path)
    tr, n_slices, n_vols, period, amp = 2.0, 4, 120, 40.0, 10.0
    slice_t = NiiMathSliceTimer.slice_times(n_slices, tr, SliceTiming.UP)
    vols = np.arange(n_vols)

    def signal(t):
        return amp * np.sin(2 * np.pi * t / period)

    data = np.zeros((3, 3, n_slices, n_vols), dtype=np.float32)
    expected = np.zeros_like(data)
    for k in range(n_slices):
        data[:, :, k, :] = signal(vols * tr + slice_t[k])
        expected[:, :, k, :] = signal(vols * tr + tr / 2)

    node = NiiMathSliceTimer()
    node.inputs.in_file = _save_series(tmp_path / "bold.nii.gz", data=data)
    node.inputs.time_repetition = tr
    node.inputs.slice_timing = SliceTiming.UP
    node.inputs.suffix = "_st"
    result = node.run()

    out = nib.load(result.outputs.out_file).get_fdata()
    assert out.shape == data.shape
    edge = 10
    core = slice(edge, n_vols - edge)

    err = np.abs(out[..., core] - expected[..., core]).max()
    uncorrected = np.abs(data[..., core] - expected[..., core]).max()
    assert uncorrected > 1.0  # the correction is actually needed
    assert err < 0.2

    # The slice acquired exactly at TR/2 is already aligned: niimath copies a
    # slice with no shift verbatim.
    k_ref = int(np.argmin(np.abs(np.array(slice_t) - tr / 2)))
    assert slice_t[k_ref] == pytest.approx(tr / 2)
    assert np.abs(out[:, :, k_ref, :] - data[:, :, k_ref, :]).max() < 1e-5
