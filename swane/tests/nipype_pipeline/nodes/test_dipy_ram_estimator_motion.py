"""Ladder/negotiation tests for
:class:`swane.nipype_pipeline.nodes.ram_estimators.DipyMotionRamEstimator`.

``DipyMotionCorrection`` registers every diffusion volume to the b0 reference
over a process pool. Its RAM has two distinct terms, and only one of them is
tunable:

* a **parent** term that scales with the whole 4D buffer -- spatial voxels
  ``V`` *times* the number of volumes ``T`` -- and is incompressible with this
  node's lever;
* a **worker** term that is a roughly fixed fraction of that parent peak per
  pool worker -- measured, not assumed: on Linux the pool forks, so each child's
  RSS also counts the copy-on-write pages inherited from the parent, and across
  11 isolated runs (V = 0.16-3.41 Mvoxel, T = 8-65, W = 1-4) the per-worker
  contribution stayed at 0.58-0.87 of the parent peak with no usable correlation
  with ``V`` alone.

The estimator therefore models ``parent(V, T) * (1 + share * W)`` and negotiates
by returning the **largest** ``W`` whose estimate fits the RAM budget, capped by
the worker count the workflow declared. Because the model is monotone in ``W``
that rung is closed-form, so no budget is left on the table: a coarser ladder
(halving, say) would drop a 10-core host to 2 workers where 3 fit, costing a
third of the throughput for nothing. Halving workers is **quality-neutral**: BLAS is pinned to one
thread inside every worker regardless of how many workers there are, so the
per-volume registration is bit-for-bit the same computation (the heavy oracle in
``test_dipy_motion.py`` and the tuned-vs-untuned test below both assert this).

These tests are deliberately **coefficient-agnostic**: every expected budget is
derived from the estimator's own model rather than from hard-coded GB figures,
so they keep their meaning when the measured constants are tuned.
"""

import os

import numpy as np
import nibabel as nib
import pytest
from nipype.pipeline.engine import Node

from swane.nipype_pipeline.nodes.DipyMotionCorrection import DipyMotionCorrection
from swane.nipype_pipeline.nodes.ram_estimators import DipyMotionRamEstimator
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)

# Big enough that the per-worker term is clearly separable from the parent term
# and from any min_gb clamp, small enough to write in milliseconds (uint8 zeros
# compress to almost nothing).
DWI_SHAPE = (96, 96, 60, 32)


def _write_dwi(tmp_path, shape=DWI_SHAPE, name="dwi"):
    """Write a zero-filled DWI plus matching bval/bvec; return the three paths.

    Only the *header* matters to the estimator (it reads the shape, never the
    data), so uint8 zeros are enough and stay cheap.
    """
    data = np.zeros(shape, dtype=np.uint8)
    in_file = str(tmp_path / f"{name}.nii.gz")
    nib.save(nib.Nifti1Image(data, np.eye(4)), in_file)

    n_vols = shape[3] if len(shape) > 3 else 1
    bvals = np.zeros((1, n_vols))
    bvals[0, 1:] = 1000
    bvecs = np.zeros((3, n_vols))
    bvecs[0, 1:] = 1.0
    bval = str(tmp_path / f"{name}.bval")
    bvec = str(tmp_path / f"{name}.bvec")
    np.savetxt(bval, bvals, fmt="%g")
    np.savetxt(bvec, bvecs, fmt="%.10f")
    return in_file, bval, bvec


def _inputs(tmp_path, num_threads=4, shape=DWI_SHAPE):
    """A populated ``DipyMotionCorrection`` input spec pointing at a real file."""
    in_file, bval, bvec = _write_dwi(tmp_path, shape)
    interface = DipyMotionCorrection()
    interface.inputs.in_file = in_file
    interface.inputs.bval = bval
    interface.inputs.bvec = bvec
    interface.inputs.num_threads = num_threads
    return interface.inputs


def _voxels_volumes(shape=DWI_SHAPE):
    return int(np.prod(shape[:3])), (shape[3] if len(shape) > 3 else 1)


def _bare_plugin(memory_gb):
    """A plugin instance without the heavy MultiProc ``__init__`` (no pool)."""
    plugin = MonitoredMultiProcPlugin.__new__(MonitoredMultiProcPlugin)
    plugin.memory_gb = memory_gb
    return plugin


class TestModel:
    """The estimate must carry voxels, volumes and workers as separate terms."""

    def test_estimate_grows_with_each_of_voxels_volumes_and_workers(self):
        est = DipyMotionRamEstimator()
        base = est.estimate_gb(voxels=500_000, volumes=32, workers=4)

        assert est.estimate_gb(voxels=1_000_000, volumes=32, workers=4) > base
        assert est.estimate_gb(voxels=500_000, volumes=64, workers=4) > base
        assert est.estimate_gb(voxels=500_000, volumes=32, workers=8) > base

    def test_worker_contribution_rides_on_the_parent_term(self):
        """Each worker costs a share of the *parent* peak, not of one volume.

        This is the measured behaviour (fork counts the parent's shared pages
        again in every child), and it has a consequence the model must keep: a
        longer series makes every worker more expensive too, so the cost of the
        pool grows with the volume count and not only with the voxel count. An
        estimator that priced workers per 3D volume would under-reserve exactly
        the many-volume acquisitions that need the reservation most.
        """
        est = DipyMotionRamEstimator()
        vox = 500_000
        short_series = est.estimate_gb(vox, 16, 4) - est.estimate_gb(vox, 16, 1)
        long_series = est.estimate_gb(vox, 64, 4) - est.estimate_gb(vox, 64, 1)
        assert long_series > short_series

    def test_serial_path_is_priced_as_a_single_worker(self, tmp_path):
        """``parallel=False`` runs in the driver process: no pool to walk."""
        inputs = _inputs(tmp_path, num_threads=4)
        inputs.parallel = False
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        mem_gb, _ = est(inputs)
        plan = est.negotiate(inputs, ram_budget_gb=0.001)

        assert mem_gb == pytest.approx(est.estimate_gb(vox, vols, 1))
        assert plan.tuned_params["num_threads"] == 1

    def test_bottom_rung_is_the_single_worker_estimate(self):
        est = DipyMotionRamEstimator()
        vox, vols = 500_000, 32
        assert est.bottom_rung_gb(vox, vols) == pytest.approx(
            est.estimate_gb(vox, vols, workers=1)
        )


class TestLadder:
    """``negotiate`` walks workers down until the estimate fits the budget."""

    def test_ample_budget_keeps_the_declared_worker_count(self, tmp_path):
        inputs = _inputs(tmp_path, num_threads=4)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        plan = est.negotiate(inputs, ram_budget_gb=est.estimate_gb(vox, vols, 4) * 4)

        assert plan.tuned_params.get("num_threads", 4) == 4
        assert plan.n_procs == 4
        assert plan.mem_gb == pytest.approx(est.estimate_gb(vox, vols, 4))

    def test_tight_budget_steps_down_to_the_expected_rung(self, tmp_path):
        inputs = _inputs(tmp_path, num_threads=4)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        full = est.estimate_gb(vox, vols, 4)
        assert full > est.estimate_gb(vox, vols, 3)
        budget = full * 0.999

        plan = est.negotiate(inputs, ram_budget_gb=budget)

        assert plan.tuned_params["num_threads"] == 3
        assert plan.n_procs == 3
        assert plan.mem_gb <= budget

    def test_picks_the_largest_worker_count_that_fits(self, tmp_path):
        """No budget left on the table on a many-core host.

        The regression this guards is a coarse ladder: halving 10 -> 5 -> 2 -> 1
        assigns 2 workers on a budget where 3 fit, a third of the throughput
        thrown away for no technical reason.
        """
        inputs = _inputs(tmp_path, num_threads=10)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        # A budget that admits exactly 3 workers and no more.
        budget = (est.estimate_gb(vox, vols, 3) + est.estimate_gb(vox, vols, 4)) / 2
        plan = est.negotiate(inputs, ram_budget_gb=budget)

        assert plan.tuned_params["num_threads"] == 3
        assert plan.n_procs == 3
        assert plan.mem_gb <= budget
        assert est.estimate_gb(vox, vols, 4) > budget

    def test_every_worker_count_from_one_to_declared_is_reachable(self, tmp_path):
        """Each rung must be selectable by some budget -- no skipped counts."""
        inputs = _inputs(tmp_path, num_threads=8)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        for expected in range(1, 9):
            budget = est.estimate_gb(vox, vols, expected)
            plan = est.negotiate(inputs, ram_budget_gb=budget)
            assert plan.tuned_params["num_threads"] == expected

    def test_impossible_budget_returns_the_bottom_rung_and_says_so(self, tmp_path):
        inputs = _inputs(tmp_path, num_threads=4)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        plan = est.negotiate(inputs, ram_budget_gb=0.001)

        assert plan.tuned_params["num_threads"] == 1
        assert plan.n_procs == 1
        assert plan.mem_gb == pytest.approx(est.bottom_rung_gb(vox, vols))
        assert "bottom" in plan.debug_str.lower()

    def test_never_raises_above_the_declared_worker_count(self, tmp_path):
        """The workflow's num_threads is a cap the estimator must not exceed."""
        inputs = _inputs(tmp_path, num_threads=2)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        plan = est.negotiate(inputs, ram_budget_gb=est.estimate_gb(vox, vols, 2) * 10)

        assert plan.tuned_params.get("num_threads", 2) == 2
        assert plan.n_procs == 2

    def test_debug_string_reports_voxels_volumes_and_the_rung(self, tmp_path):
        inputs = _inputs(tmp_path, num_threads=4)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        plan = est.negotiate(inputs, ram_budget_gb=est.estimate_gb(vox, vols, 1))

        assert str(vox) in plan.debug_str
        assert "volumes=%d" % vols in plan.debug_str
        assert "workers" in plan.debug_str.lower()


class TestOneWayCall:
    """``__call__`` (the non-negotiating path) stays the conservative one."""

    def test_call_matches_the_full_config_estimate(self, tmp_path):
        inputs = _inputs(tmp_path, num_threads=4)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        mem_gb, debug = est(inputs)

        assert mem_gb == pytest.approx(est.estimate_gb(vox, vols, 4))
        assert debug

    def test_three_dimensional_input_counts_as_one_volume(self, tmp_path):
        inputs = _inputs(tmp_path, num_threads=4, shape=(96, 96, 60))
        est = DipyMotionRamEstimator()

        mem_gb, _ = est(inputs)

        assert mem_gb == pytest.approx(est.estimate_gb(96 * 96 * 60, 1, 4))

    def test_undefined_num_threads_falls_back_to_one_worker(self, tmp_path):
        in_file, bval, bvec = _write_dwi(tmp_path)
        interface = DipyMotionCorrection()
        interface.inputs.in_file = in_file
        interface.inputs.bval = bval
        interface.inputs.bvec = bvec
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        mem_gb, _ = est(interface.inputs)

        assert mem_gb == pytest.approx(est.estimate_gb(vox, vols, 1))


class TestPluginIntegration:
    """The tuned worker count must reach both ``num_threads`` and ``n_procs``.

    ``Node.n_procs`` is bidirectional in nipype (``nodes.py:283-300``): the
    getter falls back to ``interface.inputs.num_threads`` when ``_n_procs`` was
    never set, and the setter also writes ``num_threads``. Whichever way round a
    node was configured, the scheduler must read back the tuned worker count --
    reserving 4 cores for a node the estimator just cut to 1 worker would defeat
    the negotiation.
    """

    def _node(self, tmp_path, num_threads=4, preset_n_procs=None):
        in_file, bval, bvec = _write_dwi(tmp_path)
        node = Node(DipyMotionCorrection(), name="motion", base_dir=str(tmp_path))
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.num_threads = num_threads
        if preset_n_procs is not None:
            node.n_procs = preset_n_procs
        node.ram_estimator = DipyMotionRamEstimator()
        return node

    def test_tuning_reaches_n_procs_when_it_is_derived_from_num_threads(self, tmp_path):
        """The dipy_motion case: no explicit n_procs, so it derives it."""
        node = self._node(tmp_path, num_threads=4)
        assert node._n_procs is None

        _bare_plugin(0.001)._negotiate_ram(node)

        assert node.inputs.num_threads == 1
        assert node.n_procs == 1

    def test_tuning_reaches_n_procs_when_it_was_explicitly_set(self, tmp_path):
        """A node given an explicit n_procs must not keep the stale reservation."""
        node = self._node(tmp_path, num_threads=4, preset_n_procs=4)
        assert node._n_procs == 4

        _bare_plugin(0.001)._negotiate_ram(node)

        assert node.inputs.num_threads == 1
        assert node.n_procs == 1

    def test_negotiated_reservation_lands_on_the_node(self, tmp_path):
        node = self._node(tmp_path, num_threads=4)
        est = DipyMotionRamEstimator()
        vox, vols = _voxels_volumes()

        _bare_plugin(0.001)._negotiate_ram(node)

        assert node.mem_gb_runtime == pytest.approx(est.bottom_rung_gb(vox, vols))
        assert node.ram_estimator_str


# --------------------------------------------------------------------------- #
# Tuned-vs-untuned scientific equivalence (heavy: real dipy registration)
# --------------------------------------------------------------------------- #
@pytest.mark.heavy
class TestTunedEquivalence:
    """Walking the ladder must cost wall-time only, never scientific output.

    The whole premise of the lever is that pool workers are a pure scheduling
    knob: BLAS is pinned to one thread inside each worker whatever their number,
    and results are reassembled strictly by volume index. This test runs the
    node twice on the same input -- once untuned at the declared worker count,
    once after the *real* plugin negotiation has forced the bottom rung -- and
    demands bit-for-bit identical motion-corrected series and reoriented
    gradients, with the BLAS thread environment matched on both sides.
    """

    def _run(self, work_dir, paths, num_threads, estimator=None, budget=None):
        in_file, bval, bvec = paths
        os.makedirs(work_dir, exist_ok=True)
        node = Node(DipyMotionCorrection(), name="motion", base_dir=work_dir)
        node.inputs.in_file = in_file
        node.inputs.bval = bval
        node.inputs.bvec = bvec
        node.inputs.num_threads = num_threads
        if estimator is not None:
            node.ram_estimator = estimator
            _bare_plugin(budget)._negotiate_ram(node)
        result = node.run()
        return node, result.outputs

    def test_bottom_rung_output_is_bit_for_bit_identical(self, tmp_path):
        from swane.tests.nipype_pipeline.nodes.test_dipy_motion import (
            ORACLE_ROOT,
            _make_synthetic_dwi,
        )

        os.makedirs(ORACLE_ROOT, exist_ok=True)
        in_file, bval, bvec, _ = _make_synthetic_dwi(ORACLE_ROOT, seed=7)
        paths = (in_file, bval, bvec)

        # Matched BLAS environment on both sides: loosening this would let a
        # thread-count difference, not the worker count, explain any mismatch.
        saved = {
            var: os.environ.get(var)
            for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        }
        for var in saved:
            os.environ[var] = "1"
        try:
            _, untuned = self._run(str(tmp_path / "untuned"), paths, num_threads=4)
            tuned_node, tuned = self._run(
                str(tmp_path / "tuned"),
                paths,
                num_threads=4,
                estimator=DipyMotionRamEstimator(),
                budget=0.001,
            )
        finally:
            for var, val in saved.items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val

        # The negotiation must really have moved the lever, or the comparison
        # below would be vacuous.
        assert tuned_node.inputs.num_threads == 1
        assert tuned_node.n_procs == 1

        assert np.array_equal(
            nib.load(untuned.out_file).get_fdata(),
            nib.load(tuned.out_file).get_fdata(),
        ), "tuned run changed the motion-corrected series"
        assert np.array_equal(
            np.loadtxt(untuned.out_bvec), np.loadtxt(tuned.out_bvec)
        ), "tuned run changed the reoriented gradients"
        assert np.array_equal(np.loadtxt(untuned.out_bval), np.loadtxt(tuned.out_bval))
