"""Tests for
:class:`swane.nipype_pipeline.nodes.ram_estimators.DipyCropRamEstimator`.

``DwiCrop`` loads the whole 4D series as float32 and holds it alongside the
mean-volume mask and the cropped copy -- single-threaded numpy/scipy work, no
quality-neutral lever -- so this estimator is one-way, like
:class:`DipyTissueRamEstimator`, but keyed on voxel x volume count (the 4D
regressor family shared with :class:`DipyMotionRamEstimator`/
:class:`DipyCsdRamEstimator`) rather than spatial voxels alone.

Everything runs against tiny synthetic 4D NIfTIs (nibabel/numpy) -- no test
depends on a real subject being present. The conservative-bound guard pins
three isolated tree-peak RSS measurements taken on real subject DWIs
(RAM audit, 2026-09-12); lowering the multiplier below what covers them must
fail.
"""

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.DwiCrop import DwiCrop
from swane.nipype_pipeline.nodes.ram_estimators import DipyCropRamEstimator

GB = 1024**3

# Isolated tree-peak RSS of the real node on three real subject DWIs
# (voxel x volume -> measured GB), 2026-09-12. The conservative bound must sit
# above all three.
MEASURED_PEAKS = {
    54_525_952: 0.532,  # subj1, 256x256x52x16
    80_870_400: 1.153,  # subj2, 144x144x60x65
    167_731_200: 2.425,  # subj3, 192x192x70x65
}


def _write_dwi(tmp_path, shape, name="dwi"):
    """Write a zero-filled 4D DWI; return its path.

    Only the header (shape) matters to the estimator -- it never reads the
    data -- so uint8 zeros stay cheap.
    """
    data = np.zeros(shape, dtype=np.uint8)
    path = str(tmp_path / f"{name}.nii.gz")
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return path


def _inputs(tmp_path, shape, name="dwi"):
    interface = DwiCrop()
    interface.inputs.in_file = _write_dwi(tmp_path, shape, name=name)
    return interface.inputs


def _expected_gb(est, voxels, volumes):
    raw = est.OVERHEAD_GB + est.BYTES_PER_VOXEL_VOLUME * voxels * volumes / GB
    return max(est.MIN_GB, raw)


class TestModel:
    """The estimate tracks voxel x volume count and nothing else."""

    def test_estimate_grows_with_volumes(self, tmp_path):
        # Both shapes are large enough that the estimate clears MIN_GB, so the
        # comparison actually exercises the voxel x volume term.
        est = DipyCropRamEstimator()
        few, _ = est(_inputs(tmp_path, (100, 100, 60, 20), name="few"))
        many, _ = est(_inputs(tmp_path, (100, 100, 60, 80), name="many"))
        assert many > few

    def test_estimate_matches_the_voxel_volume_formula(self, tmp_path):
        est = DipyCropRamEstimator()
        shape = (100, 100, 60, 30)  # comfortably above the min floor
        mem_gb, debug = est(_inputs(tmp_path, shape))
        voxels = shape[0] * shape[1] * shape[2]
        assert mem_gb == pytest.approx(_expected_gb(est, voxels, shape[3]))
        assert debug

    def test_3d_input_is_treated_as_a_single_volume(self, tmp_path):
        est = DipyCropRamEstimator()
        mem_gb, _ = est(_inputs(tmp_path, (100, 100, 60)))
        voxels = 100 * 100 * 60
        assert mem_gb == pytest.approx(_expected_gb(est, voxels, 1))

    def test_tiny_input_respects_the_min_floor(self, tmp_path):
        est = DipyCropRamEstimator()
        mem_gb, _ = est(_inputs(tmp_path, (4, 4, 4, 2)))
        assert mem_gb == pytest.approx(est.MIN_GB)


class TestConservativeBound:
    """The bound must over-estimate the real node on the measured subjects."""

    @pytest.mark.parametrize("voxel_volumes,measured", MEASURED_PEAKS.items())
    def test_estimate_exceeds_the_measured_peak(self, voxel_volumes, measured):
        est = DipyCropRamEstimator()
        mem_gb = est.estimate_gb(voxel_volumes, 1)
        assert mem_gb > measured

    def test_large_input_is_not_clamped_down(self, tmp_path):
        """max_gb is None: a big DWI must reserve its full modelled peak."""
        est = DipyCropRamEstimator()
        assert est.max_gb is None
        shape = (300, 300, 200, 80)  # far above every measured subject
        mem_gb, _ = est(_inputs(tmp_path, shape))
        voxels = shape[0] * shape[1] * shape[2]
        assert mem_gb == pytest.approx(_expected_gb(est, voxels, shape[3]))
        assert mem_gb > 10


class TestClassicNegotiation:
    """No lever: the inherited negotiate reserves RAM and tunes nothing."""

    def test_negotiate_returns_the_call_estimate_with_empty_tuning(self, tmp_path):
        est = DipyCropRamEstimator()
        inputs = _inputs(tmp_path, (100, 100, 60, 30))
        mem_gb, _ = est(inputs)

        plan = est.negotiate(inputs, ram_budget_gb=0.001)

        assert plan.tuned_params == {}
        assert plan.n_procs is None
        assert plan.mem_gb == pytest.approx(mem_gb)
