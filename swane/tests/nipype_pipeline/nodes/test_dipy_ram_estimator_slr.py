"""Tests for
:class:`swane.nipype_pipeline.nodes.ram_estimators.DipySlrRamEstimator`.

``DipyAtlasSLR`` fits dipy's ``whole_brain_slr`` on a fixed-size subsample of
the subject tractogram, applies the affine to the full tractogram in place and
streams the write, so the peak tracks the full tractogram's point count.
``num_threads`` only pins BLAS/OMP threading and the subsample size is fixed --
so this estimator is one-way, like
:class:`DipyTissueRamEstimator`/:class:`RecoBundlesRamEstimator`, keyed on the
subject tractogram's point count.

Everything runs against tiny synthetic ``.trx`` phantoms (nibabel/numpy/dipy)
-- no test depends on a real subject being present. The conservative-bound
guard pins three isolated tree-peak RSS measurements taken on real,
current-pipeline subject tractograms (RAM audit, 2026-09-13); lowering the
multiplier below what covers them must fail.

``ResourceManager.dipy_tractography_ram_requirements`` and
``DipySlrRamEstimator.STATIC_FALLBACK_GB`` must never drift apart -- see
``TestResourceManagerAlignment``.
"""

import numpy as np
import nibabel as nib
import pytest

from nipype import Node

from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)
from swane.nipype_pipeline.nodes.DipyAtlasSLR import DipyAtlasSLR
from swane.nipype_pipeline.nodes.ram_estimators import DipySlrRamEstimator
from swane.utils.ResourceManager import ResourceManager

GB = 1024**3

# Isolated peak RSS across representative tractograms (points -> measured GB).
# The conservative bound must sit above all three.
MEASURED_PEAKS = {
    121_088_164: 4.348,
    67_925_234: 3.643,
    119_653_463: 4.386,
}


def _phantom_trx(path, n_streamlines, pts_per_streamline=4):
    """Write a synthetic ``.trx`` with a known streamline/point count."""
    from dipy.io.streamline import save_tractogram
    from dipy.io.stateful_tractogram import StatefulTractogram, Space

    img = nib.Nifti1Image(np.zeros((5, 5, 5), dtype=np.float32), np.eye(4))
    sls = [
        (np.random.rand(pts_per_streamline, 3).astype(np.float32) * 4)
        for _ in range(n_streamlines)
    ]
    sft = StatefulTractogram(sls, img, Space.RASMM)
    save_tractogram(sft, str(path), bbox_valid_check=False)
    return str(path)


def _bare_plugin(memory_gb):
    plugin = MonitoredMultiProcPlugin.__new__(MonitoredMultiProcPlugin)
    plugin.memory_gb = memory_gb
    return plugin


class TestModel:
    """The pure-arithmetic model, exercised without any file."""

    def test_estimate_is_overhead_plus_per_point(self):
        est = DipySlrRamEstimator()
        points = 100_000_000
        expected = est.OVERHEAD_GB + est.BYTES_PER_POINT * points / GB
        assert est.estimate_gb(points) == pytest.approx(expected)

    def test_estimate_floored_at_fixed_overhead(self):
        est = DipySlrRamEstimator()
        # An empty tractogram still reserves the fixed overhead (atlas load,
        # dipy imports, trx machinery), which exceeds MIN_GB.
        assert est.estimate_gb(0) == pytest.approx(est.OVERHEAD_GB)

    def test_estimate_monotone_in_points(self):
        est = DipySlrRamEstimator()
        assert est.estimate_gb(10_000_000) < est.estimate_gb(20_000_000)


class TestReadsHeader:
    """The estimator reads the point count from the ``.trx`` header."""

    def test_call_matches_model(self, tmp_path):
        path = _phantom_trx(
            tmp_path / "tractogram.trx", n_streamlines=300, pts_per_streamline=6
        )
        est = DipySlrRamEstimator()

        class _Inputs:
            tractogram = path

        mem_gb, debug = est(_Inputs())
        assert mem_gb == pytest.approx(est.estimate_gb(300 * 6))
        assert "points=1800" in debug and "streamlines=300" in debug


class TestConservativeBound:
    """The bound must over-estimate the real node on the measured subjects."""

    @pytest.mark.parametrize("n_points,measured", MEASURED_PEAKS.items())
    def test_estimate_exceeds_the_measured_peak(self, n_points, measured):
        est = DipySlrRamEstimator()
        assert est.estimate_gb(n_points) > measured

    def test_large_input_is_not_clamped_down(self):
        """max_gb is None: a big tractogram must reserve its full modelled peak."""
        est = DipySlrRamEstimator()
        assert est.max_gb is None
        mem_gb = est.estimate_gb(500_000_000)  # far above every measured subject
        assert mem_gb > 10


class TestClassicNegotiation:
    """No lever: the inherited negotiate reserves RAM and tunes nothing."""

    def test_negotiate_returns_the_call_estimate_with_empty_tuning(self, tmp_path):
        path = _phantom_trx(tmp_path / "tractogram.trx", n_streamlines=200)
        est = DipySlrRamEstimator()

        class _Inputs:
            tractogram = path

        inputs = _Inputs()
        mem_gb, _ = est(inputs)

        plan = est.negotiate(inputs, ram_budget_gb=0.001)

        assert plan.tuned_params == {}
        assert plan.n_procs is None
        assert plan.mem_gb == pytest.approx(mem_gb)


class TestPluginIntegration:
    """Through the real plugin the node is reserved but never mutated."""

    def test_reservation_lands_on_the_node_without_tuning(self, tmp_path):
        path = _phantom_trx(tmp_path / "tractogram.trx", n_streamlines=250)
        node = Node(DipyAtlasSLR(), name="dipy_slr", base_dir=str(tmp_path))
        node.inputs.tractogram = path
        node.inputs.atlas_dir = str(tmp_path)
        node._mem_gb = DipySlrRamEstimator.STATIC_FALLBACK_GB
        node.n_procs = 1
        node.ram_estimator = DipySlrRamEstimator()

        _bare_plugin(0.001)._negotiate_ram(node)

        est = DipySlrRamEstimator()
        assert node.mem_gb_runtime == pytest.approx(est(node.inputs)[0])
        assert node.n_procs == 1  # unchanged: n_procs=None keeps the declared value
        assert node.inputs.tractogram == path  # inputs untouched
        assert node.ram_estimator_str


class TestResourceManagerAlignment:
    """The node's static fall-back must never exceed the engine gate."""

    def test_static_fallback_matches_the_preference_gate(self):
        assert (
            DipySlrRamEstimator.STATIC_FALLBACK_GB
            == ResourceManager.dipy_tractography_ram_requirements()
        )
