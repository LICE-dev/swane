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

from nipype.utils.ram_estimator import RamEstimator

from swane.nipype_pipeline.nodes.ram_estimators import (
    FlirtRamEstimator,
    FnirtRamEstimator,
    InvWarpRamEstimator,
    FastRamEstimator,
)


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
        assert isinstance(est, RamEstimator)
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
