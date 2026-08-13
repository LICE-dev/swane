"""Unit tests for the RAM estimation helpers.

Covers :class:`swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.NipypeRamEstimator`
and the calibrated subclasses in
:mod:`swane.nipype_pipeline.nodes.ram_estimators`.

The estimator inspects a node's nipype input traits and turns them into a
memory estimate: file inputs contribute through their spatial voxel count,
numeric inputs contribute through their value, and the total is offset by a
fixed overhead and clamped to ``[min_gb, max_gb]``. These tests exercise that
pure-Python arithmetic against tiny synthetic NIfTI volumes generated with
nibabel/numpy, so no FSL/FreeSurfer installation is needed.
"""

import numpy as np
import nibabel as nib
import pytest
from nipype.interfaces.base import BaseInterfaceInputSpec, File, traits

from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    NipypeRamEstimator,
)
from swane.nipype_pipeline.nodes.ram_estimators import (
    FlirtRamEstimator,
    FnirtRamEstimator,
    InvWarpRamEstimator,
    FastRamEstimator,
)

# One GB expressed in voxels so that "multiplier == GB_IN_VOXELS" makes a
# file's contribution equal exactly its spatial voxel count (in GB), cancelling
# the /1024**3 division inside the estimator and keeping assertions exact.
GB_IN_VOXELS = 1024**3


class _DummyInputSpec(BaseInterfaceInputSpec):
    """Minimal nipype input spec exposing file, list and numeric traits.

    It stands in for a real node's ``inputs`` object so the estimator can be
    driven with fully controlled trait values.
    """

    in_file = File(exists=False)
    reference = File(exists=False)
    files = traits.List(File(exists=False))
    scalar = traits.Int()
    numbers = traits.List(traits.Float())


def _write_nifti(path, shape):
    """Write a tiny all-zero NIfTI of the given shape and return its path."""
    data = np.zeros(shape, dtype=np.uint8)
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(path))
    return str(path)


class TestClamp:
    """The static :meth:`NipypeRamEstimator.clamp` bounding helper."""

    def test_clamps_to_max(self):
        """A value above ``max_val`` is pulled down to ``max_val``."""
        assert NipypeRamEstimator.clamp(5.0, 1.0, 4.0) == 4.0

    def test_clamps_to_min(self):
        """A value below ``min_val`` is pushed up to ``min_val``."""
        assert NipypeRamEstimator.clamp(0.1, 1.0, 4.0) == 1.0

    def test_value_in_range_is_unchanged(self):
        """A value already within the bounds passes through untouched."""
        assert NipypeRamEstimator.clamp(2.5, 1.0, 4.0) == 2.5

    def test_none_bounds_are_ignored(self):
        """Passing ``None`` for both bounds disables clamping entirely."""
        assert NipypeRamEstimator.clamp(123.0, None, None) == 123.0


class TestVoxels:
    """The static :meth:`NipypeRamEstimator.voxels` volume-size helper."""

    def test_ignores_time_dimension(self, tmp_path):
        """Only the first three (spatial) dimensions are counted.

        A 4D image must report the same voxel count as its single volume, so
        the estimate does not scale with the number of timepoints.
        """
        path = _write_nifti(tmp_path / "vol4d.nii.gz", (4, 5, 6, 7))
        assert NipypeRamEstimator.voxels(path) == 4 * 5 * 6

    def test_three_d_volume(self, tmp_path):
        """A plain 3D volume reports the product of its three dimensions."""
        path = _write_nifti(tmp_path / "vol3d.nii.gz", (2, 3, 4))
        assert NipypeRamEstimator.voxels(path) == 24


class TestNipypeRamEstimatorCall:
    """The ``__call__`` aggregation logic over a node's input traits."""

    def _inputs(self, **values):
        """Build a :class:`_DummyInputSpec` with the given trait values set."""
        inputs = _DummyInputSpec()
        for key, val in values.items():
            setattr(inputs, key, val)
        return inputs

    def test_returns_float_and_debug_string(self, tmp_path):
        """The estimator returns a ``(mem_gb, debug_string)`` pair.

        ``mem_gb`` must be a plain float (consumed as a nipype ``mem_gb``) and
        the second element a human-readable breakdown for the node report.
        """
        path = _write_nifti(tmp_path / "a.nii.gz", (2, 2, 2))
        est = NipypeRamEstimator(
            input_multipliers={"in_file": GB_IN_VOXELS},
            overhead_gb=0.0,
            min_gb=0.0,
            max_gb=1e9,
        )
        mem_gb, debug = est(self._inputs(in_file=path))
        assert isinstance(mem_gb, float)
        assert isinstance(debug, str)

    def test_file_contribution_uses_voxel_count(self, tmp_path):
        """A file input contributes ``voxels * multiplier / 1024**3`` GB.

        With ``multiplier == GB_IN_VOXELS`` the division cancels, so a 2x2x2
        volume contributes exactly its 8 voxels as 8 GB.
        """
        path = _write_nifti(tmp_path / "a.nii.gz", (2, 2, 2))
        est = NipypeRamEstimator(
            input_multipliers={"in_file": GB_IN_VOXELS},
            overhead_gb=0.0,
            min_gb=0.0,
            max_gb=1e9,
        )
        mem_gb, _ = est(self._inputs(in_file=path))
        assert mem_gb == pytest.approx(8.0)

    def test_list_of_files_sums_voxels(self, tmp_path):
        """A list-of-files input sums the voxel counts of every entry."""
        p1 = _write_nifti(tmp_path / "a.nii.gz", (2, 2, 2))  # 8 voxels
        p2 = _write_nifti(tmp_path / "b.nii.gz", (2, 2, 3))  # 12 voxels
        est = NipypeRamEstimator(
            input_multipliers={"files": GB_IN_VOXELS},
            overhead_gb=0.0,
            min_gb=0.0,
            max_gb=1e9,
        )
        mem_gb, _ = est(self._inputs(files=[p1, p2]))
        assert mem_gb == pytest.approx(20.0)

    def test_overhead_is_added(self, tmp_path):
        """The fixed ``overhead_gb`` is added on top of the input contributions."""
        path = _write_nifti(tmp_path / "a.nii.gz", (2, 2, 2))
        est = NipypeRamEstimator(
            input_multipliers={"in_file": GB_IN_VOXELS},
            overhead_gb=1.5,
            min_gb=0.0,
            max_gb=1e9,
        )
        mem_gb, _ = est(self._inputs(in_file=path))
        assert mem_gb == pytest.approx(8.0 + 1.5)

    def test_numeric_input_contributes_directly(self):
        """A numeric input contributes ``value * multiplier`` GB directly.

        Unlike files, scalar traits are not divided by ``1024**3``.
        """
        est = NipypeRamEstimator(
            input_multipliers={"scalar": 10},
            overhead_gb=0.0,
            min_gb=0.0,
            max_gb=1e9,
        )
        mem_gb, _ = est(self._inputs(scalar=5))
        assert mem_gb == pytest.approx(50.0)

    def test_numeric_result_is_clamped_to_max(self):
        """An oversized estimate is capped at ``max_gb``."""
        est = NipypeRamEstimator(
            input_multipliers={"scalar": 10},
            overhead_gb=0.0,
            min_gb=0.0,
            max_gb=100.0,
        )
        mem_gb, _ = est(self._inputs(scalar=20))  # 200 -> clamped to 100
        assert mem_gb == 100.0

    def test_result_is_clamped_to_min_when_all_undefined(self):
        """With every input undefined the estimate floors at ``min_gb``.

        Undefined traits contribute nothing and are flagged in the debug
        string, so only the overhead remains before the minimum clamp applies.
        """
        est = NipypeRamEstimator(
            input_multipliers={"in_file": GB_IN_VOXELS},
            overhead_gb=0.0,
            min_gb=2.0,
            max_gb=100.0,
        )
        mem_gb, debug = est(self._inputs())  # nothing set
        assert mem_gb == 2.0
        assert "undefined" in debug

    def test_missing_trait_is_reported(self):
        """A multiplier for an unknown trait is skipped and reported.

        The estimate falls back to the overhead only, and the debug string
        records that the trait was not found.
        """
        est = NipypeRamEstimator(
            input_multipliers={"does_not_exist": 10},
            overhead_gb=0.5,
            min_gb=0.0,
            max_gb=100.0,
        )
        mem_gb, debug = est(self._inputs())
        assert "trait not found" in debug
        assert mem_gb == pytest.approx(0.5)  # overhead only

    def test_nonexistent_file_path_contributes_nothing(self, tmp_path):
        """A defined-but-missing file path adds no memory.

        The path is a valid string (so the trait is 'defined') but does not
        exist on disk, so it is skipped and the debug string notes that no
        readable image files were found.
        """
        est = NipypeRamEstimator(
            input_multipliers={"in_file": GB_IN_VOXELS},
            overhead_gb=0.3,
            min_gb=0.0,
            max_gb=100.0,
        )
        mem_gb, debug = est(self._inputs(in_file=str(tmp_path / "missing.nii.gz")))
        assert mem_gb == pytest.approx(0.3)
        assert "no readable image files" in debug


class TestCalibratedEstimators:
    """The concrete, pre-calibrated estimators used by the real nodes."""

    # (estimator class, expected multipliers, overhead, min_gb, max_gb)
    CASES = [
        (FlirtRamEstimator, {"in_file": 12, "reference": 2}, 0.30, 0.3, 4.0),
        (FnirtRamEstimator, {"in_file": 24, "ref_file": 200}, 1.8, 2, 8.0),
        (InvWarpRamEstimator, {"warp": 2, "reference": 48}, 0.3, 0.4, 6.0),
        (FastRamEstimator, {"in_files": 110}, 0.3, 1, 8),
    ]

    @pytest.mark.parametrize("cls, multipliers, overhead, min_gb, max_gb", CASES)
    def test_calibration_constants(self, cls, multipliers, overhead, min_gb, max_gb):
        """Each subclass keeps its empirically calibrated constants.

        These numbers were tuned from real ``mem_peak_gb`` measurements, so
        this test freezes them against accidental edits/regressions.
        """
        est = cls()
        assert isinstance(est, NipypeRamEstimator)
        assert est.input_multipliers == multipliers
        assert est.overhead_gb == overhead
        assert est.min_gb == min_gb
        assert est.max_gb == max_gb

    def test_estimator_is_callable_and_stays_within_bounds(self, tmp_path):
        """A real estimator on a tiny image yields a bounded, overhead-sized value.

        The image contributes a negligible amount, so the estimate is dominated
        by the overhead and must stay within ``[min_gb, max_gb]``.
        """
        data = np.zeros((3, 3, 3), dtype=np.uint8)
        path = str(tmp_path / "small.nii.gz")
        nib.save(nib.Nifti1Image(data, np.eye(4)), path)

        class _FlirtInputs(BaseInterfaceInputSpec):
            in_file = File(exists=False)
            reference = File(exists=False)

        inputs = _FlirtInputs()
        inputs.in_file = path
        inputs.reference = path

        est = FlirtRamEstimator()
        mem_gb, debug = est(inputs)
        assert est.min_gb <= mem_gb <= est.max_gb
        assert mem_gb == pytest.approx(est.overhead_gb, abs=1e-2)
        assert isinstance(debug, str)
