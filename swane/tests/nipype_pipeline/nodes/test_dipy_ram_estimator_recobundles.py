"""Unit tests for the RecoBundles RAM estimators (build/recognise + chunker).

The estimator models the build and recognise nodes' peak as linear in the
loaded chunk's total point count, read from the ``.trx`` header, and the chunker
estimator inverts that model to choose ``n_chunks`` at scheduling time so each
downstream chunk fits the RAM budget.

Everything runs against tiny synthetic ``.trx`` phantoms (nibabel/numpy/dipy) or
pure arithmetic -- no test depends on a real subject being present.
"""

import numpy as np
import nibabel as nib
import pytest

from nipype import Node

from swane.patches.nipype_patches import RamPlan
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)
from swane.nipype_pipeline.nodes.ram_estimators import (
    RecoBundlesRamEstimator,
    DipyRecoBundlesChunkerRamEstimator,
)
from swane.nipype_pipeline.nodes.DipyTractogramChunker import DipyTractogramChunker
from swane.nipype_pipeline.nodes.DipyRecoBundles import DipyRecoBundlesBuild

GB = 1024**3


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
        est = RecoBundlesRamEstimator()
        points = 50_000_000
        expected = est.OVERHEAD_GB + est.BYTES_PER_POINT * points / GB
        assert est.estimate_gb(points) == pytest.approx(expected)

    def test_estimate_floored_at_min_gb(self):
        est = RecoBundlesRamEstimator()
        assert est.estimate_gb(0) == pytest.approx(est.MIN_GB)

    def test_estimate_monotone_in_points(self):
        est = RecoBundlesRamEstimator()
        assert est.estimate_gb(10_000_000) < est.estimate_gb(20_000_000)

    def test_max_chunks_from_streamline_floor(self):
        est = RecoBundlesRamEstimator()
        floor = est.MIN_STREAMLINES_PER_CHUNK
        assert est.max_chunks(floor - 1) == 1
        assert est.max_chunks(3 * floor) == 3
        assert est.max_chunks(0) == 1

    def test_ample_budget_gives_one_chunk(self):
        est = RecoBundlesRamEstimator()
        # A whole tractogram whose estimate is well under the budget.
        n = est.min_chunks_for_budget(
            total_points=60_000_000, n_streamlines=300_000, ram_budget_gb=64.0
        )
        assert n == 1

    def test_tight_budget_splits_but_respects_floor_cap(self):
        est = RecoBundlesRamEstimator()
        # Huge tractogram, tiny budget: n is capped at n_streamlines // floor.
        cap = est.max_chunks(250_000)  # == 2
        n = est.min_chunks_for_budget(
            total_points=2_000_000_000, n_streamlines=250_000, ram_budget_gb=1.0
        )
        assert n == cap == 2

    def test_split_is_smallest_n_that_fits(self):
        est = RecoBundlesRamEstimator()
        total_points = 400_000_000
        n_streamlines = 10_000_000  # a high floor cap, so RAM is the binding limit
        budget = est.estimate_gb(total_points) - 1.0  # n=1 does not fit
        n = est.min_chunks_for_budget(total_points, n_streamlines, budget)
        # every chunk fits ...
        assert est.estimate_gb(total_points / n) <= budget
        # ... and one fewer chunk would not
        assert est.estimate_gb(total_points / (n - 1)) > budget

    def test_monotone_in_budget(self):
        est = RecoBundlesRamEstimator()
        args = dict(total_points=400_000_000, n_streamlines=10_000_000)
        tight = est.min_chunks_for_budget(ram_budget_gb=4.0, **args)
        loose = est.min_chunks_for_budget(ram_budget_gb=8.0, **args)
        assert tight >= loose >= 1

    def test_non_positive_headroom_returns_cap(self):
        est = RecoBundlesRamEstimator()
        n = est.min_chunks_for_budget(
            total_points=10_000_000,
            n_streamlines=500_000,
            ram_budget_gb=est.OVERHEAD_GB,  # zero headroom
        )
        assert n == est.max_chunks(500_000)


class TestReadsHeader:
    """The estimators read counts from the ``.trx`` header."""

    def test_build_recognise_call_matches_model(self, tmp_path):
        path = _phantom_trx(
            tmp_path / "chunk.trx", n_streamlines=200, pts_per_streamline=6
        )
        est = RecoBundlesRamEstimator()

        class _Inputs:
            tractogram_chunk = path

        mem_gb, debug = est(_Inputs())
        assert mem_gb == pytest.approx(est.estimate_gb(200 * 6))
        assert "points=1200" in debug and "streamlines=200" in debug

    def test_chunker_call_reads_whole_tractogram(self, tmp_path):
        path = _phantom_trx(
            tmp_path / "atlas.trx", n_streamlines=150, pts_per_streamline=8
        )
        est = DipyRecoBundlesChunkerRamEstimator()

        class _Inputs:
            tractogram_atlas = path

        mem_gb, _ = est(_Inputs())
        assert mem_gb == pytest.approx(est.estimate_gb(150 * 8))


class TestChunkerNegotiate:
    """negotiate injects n_chunks and reserves the chunker's own RAM."""

    def test_ample_budget_injects_one_chunk(self, tmp_path):
        path = _phantom_trx(tmp_path / "atlas.trx", n_streamlines=500)
        est = DipyRecoBundlesChunkerRamEstimator()

        class _Inputs:
            tractogram_atlas = path

        plan = est.negotiate(_Inputs(), ram_budget_gb=32.0)
        assert isinstance(plan, RamPlan)
        assert plan.tuned_params == {"n_chunks": 1}
        assert plan.n_procs is None
        assert plan.mem_gb == pytest.approx(est.estimate_gb(500 * 4))

    def test_tight_budget_injects_more_than_one_chunk(self, tmp_path, monkeypatch):
        # A small phantom cannot reach the 100k streamline floor, so lower it
        # for the test; the arithmetic path is what matters here.
        path = _phantom_trx(
            tmp_path / "atlas.trx", n_streamlines=900, pts_per_streamline=10
        )
        est = DipyRecoBundlesChunkerRamEstimator()
        monkeypatch.setattr(est._downstream, "MIN_STREAMLINES_PER_CHUNK", 100)
        # Budget just above overhead: headroom is tiny, so the split is forced.
        headroom = 1e-4
        plan = est.negotiate(
            est_inputs(path), ram_budget_gb=est._downstream.OVERHEAD_GB + headroom
        )
        assert plan.tuned_params["n_chunks"] > 1
        assert plan.tuned_params["n_chunks"] <= est._downstream.max_chunks(900)


def est_inputs(path):
    class _Inputs:
        tractogram_atlas = path

    return _Inputs()


class TestPluginIntegration:
    """The plugin hook applies the plan to the real nodes."""

    def test_chunker_node_gets_n_chunks_tuned_onto_inputs(self, tmp_path):
        path = _phantom_trx(tmp_path / "atlas.trx", n_streamlines=400)
        node = Node(DipyTractogramChunker(), name="chunker")
        node.inputs.tractogram_atlas = path
        node.ram_estimator = DipyRecoBundlesChunkerRamEstimator()

        _bare_plugin(32.0)._negotiate_ram(node)

        assert node.inputs.n_chunks == 1
        assert node._ram_estimated is True
        assert node.mem_gb_runtime == pytest.approx(
            node.ram_estimator.estimate_gb(400 * 4)
        )

    def test_build_node_reserves_from_chunk_points(self, tmp_path):
        path = _phantom_trx(
            tmp_path / "chunk.trx", n_streamlines=250, pts_per_streamline=5
        )
        node = Node(DipyRecoBundlesBuild(), name="build")
        node.inputs.tractogram_chunk = path
        node.ram_estimator = RecoBundlesRamEstimator()

        _bare_plugin(32.0)._negotiate_ram(node)

        assert node._ram_estimated is True
        assert node.mem_gb_runtime == pytest.approx(
            node.ram_estimator.estimate_gb(250 * 5)
        )
