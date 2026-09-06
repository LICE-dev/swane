"""Tests for
:class:`swane.nipype_pipeline.nodes.ram_estimators.DipyCsdRamEstimator`.

``DipyCsdFit`` runs dipy's ``peaks_from_model``, whose two branches have
**structurally different** memory profiles -- which is what shapes this
estimator and its ladder:

* **Serial** (``num_processes == 1``) allocates one full-volume set of output
  arrays (``gfa``, ``qa``, ``peak_dirs``, ``peak_values``, ``peak_indices``,
  ``shm_coeff``).
* **Parallel** (``num_processes > 1``) splits the data into ``P**2`` chunks and
  holds *three* full-volume equivalents at once: every chunk result returned by
  ``pool.map`` lives in the parent simultaneously, they are copied into
  ``np.memmap`` buffers, and those are read back with ``np.array``.
* Each of the ``P`` concurrent workers additionally holds its chunk's arrays
  (``voxels / P**2`` each), so the aggregate worker term scales as
  ``voxels / P`` -- it *shrinks* as ``P`` grows -- plus one ``spawn``
  interpreter per worker.

The consequence is that RAM **need not be monotone in P**: the parent term is
constant in ``P`` while the worker term falls as ``1/P`` and the spawn term
grows linearly, so above a volume threshold a *lower* rung costs *more* and a
naive halving ladder does not converge downwards. The real cliff is ``P == 1``,
which switches to the serial branch and drops two of the three full-volume
copies. ``negotiate`` therefore evaluates every rung and returns the largest
``P`` that fits, with the serial rung as the floor.

Where they can be, these tests are **coefficient-agnostic**: expected figures
are derived from the estimator's own constants, so they keep their meaning if
the bound is retuned. The exception is the conservative-bound guard, which pins
the *measured* oracle peaks on purpose -- lowering a multiplier below what
covers the oracles must fail.
"""

import glob
import gzip
import os
import pickle

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.DipyCsdFit import DipyCsdFit
from swane.nipype_pipeline.nodes.ram_estimators import DipyCsdRamEstimator

# Importing the plugin applies the SWANe nipype patches, which add
# RamEstimator.negotiate and RamPlan.
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (  # noqa: F401
    MonitoredMultiProcPlugin,
)


def _write_dwi(tmp_path, shape, name="dwi"):
    """Write a header-only 4D DWI; return its path.

    The estimator reads the shape out of the header and never touches the voxel
    data, so only the 352-byte header is written. That keeps the oracle-sized
    and above-oracle-sized shapes these tests need (tens of millions of voxels
    across dozens of volumes) free instead of hundreds of megabytes each.
    """
    header = nib.Nifti1Header()
    header.set_data_shape(shape)
    header.set_data_dtype(np.uint8)
    path = str(tmp_path / f"{name}.nii")
    with open(path, "wb") as handle:
        header.write_to(handle)
    return path


def _write_gradients(tmp_path, n_directions, n_b0=1, name="dwi"):
    """Write a single-shell bval/bvec pair: ``n_b0`` b0s and ``n_directions``
    diffusion-weighted volumes. The total volume count deliberately differs from
    the direction count so the tests can tell the two apart. Both files are
    written because the estimator builds the same gradient table the node does.
    """
    rng = np.random.default_rng(3)
    dirs = rng.normal(size=(n_directions, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    bvals = np.concatenate([np.zeros(n_b0), np.full(n_directions, 1000.0)])
    bvecs = np.vstack([np.zeros((n_b0, 3)), dirs])
    bval_path = tmp_path / f"{name}.bval"
    bvec_path = tmp_path / f"{name}.bvec"
    np.savetxt(bval_path, bvals[None, :], fmt="%g")
    np.savetxt(bvec_path, bvecs.T, fmt="%.6f")
    return str(bval_path), str(bvec_path)


def _inputs(tmp_path, shape, n_directions, n_b0=1, num_threads=4):
    """A populated ``DipyCsdFit`` input spec the estimator can read."""
    node = DipyCsdFit()
    node.inputs.in_file = _write_dwi(tmp_path, shape)
    node.inputs.bval, node.inputs.bvec = _write_gradients(tmp_path, n_directions, n_b0)
    node.inputs.num_threads = num_threads
    return node.inputs


def _coeff(sh_order):
    return (sh_order + 1) * (sh_order + 2) // 2


def _non_monotone_voxels(est, n_coeff, low=2, high=4):
    """Smallest voxel count for which ``estimate_gb`` at ``low`` workers exceeds
    the estimate at ``high``, derived from the estimator's own constants.

    ``estimate(low) - estimate(high)`` is
    ``per_voxel * V * (1/low - 1/high) - (high - low) * SPAWN``, so the regime
    starts at ``V = (high - low) * SPAWN * 2**30 / (per_voxel * (1/low -
    1/high))``. Deriving it keeps the test meaningful after a recalibration
    instead of pinning a shape that happens to sit in the regime today.
    """
    per_voxel = est.per_voxel_bytes(n_coeff)
    gap = 1.0 / low - 1.0 / high
    threshold = (high - low) * est.SPAWN_GB_PER_WORKER * 1024**3 / (per_voxel * gap)
    return int(threshold * 2)  # comfortably inside the regime


class TestModelShape:
    """The estimate is driven by the input sequence's voxels and volumes."""

    def test_reads_voxels_and_volumes_from_the_header(self, tmp_path):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (16, 15, 14, 20), n_directions=19)
        assert est._shape(inputs) == (16 * 15 * 14, 20)

    def test_estimate_grows_with_spatial_voxels(self, tmp_path):
        est = DipyCsdRamEstimator()
        small = est.estimate_gb(1_000_000, 30, _coeff(6), 4)
        big = est.estimate_gb(2_000_000, 30, _coeff(6), 4)
        assert big > small

    def test_estimate_grows_with_volumes(self, tmp_path):
        est = DipyCsdRamEstimator()
        few = est.estimate_gb(1_000_000, 20, _coeff(6), 4)
        many = est.estimate_gb(1_000_000, 60, _coeff(6), 4)
        assert many > few

    def test_estimate_grows_with_sh_coefficients(self):
        est = DipyCsdRamEstimator()
        low = est.estimate_gb(1_000_000, 30, _coeff(4), 4)
        high = est.estimate_gb(1_000_000, 30, _coeff(8), 4)
        assert high > low


class TestShOrderFromBval:
    """The SH order comes from the non-b0 direction count in the bval file."""

    @pytest.mark.parametrize(
        "n_directions, expected_sh",
        [(64, 8), (30, 6), (15, 4), (6, 2)],
    )
    def test_n_coeff_follows_the_direction_table(
        self, tmp_path, n_directions, expected_sh
    ):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (8, 8, 8, n_directions + 1), n_directions)
        assert est._n_coeff(inputs) == _coeff(expected_sh)

    def test_extra_b0_volumes_do_not_inflate_the_sh_order(self, tmp_path):
        # 30 directions -> lmax 6 whatever the b0 padding; a naive volume count
        # (35) would wrongly reach lmax 6 too, so compare against the b0-heavy
        # case that a volume count would push over the lmax 8 boundary.
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (8, 8, 8, 50), n_directions=30, n_b0=20)
        assert est._n_coeff(inputs) == _coeff(6)


class TestTwoRegimes:
    """Serial and parallel are different models, not two points on one curve."""

    def test_serial_holds_one_full_volume_copy_parallel_three(self):
        est = DipyCsdRamEstimator()
        voxels, volumes, n_coeff = 2_000_000, 40, _coeff(8)
        per_voxel = est.per_voxel_bytes(n_coeff) / 1024**3
        data = est.DATA_BYTES_PER_VOXEL_VOLUME * voxels * volumes / 1024**3

        serial = est.estimate_gb(voxels, volumes, n_coeff, 1)
        assert serial == pytest.approx(
            est.OVERHEAD_GB + data + est.SERIAL_COPIES * per_voxel * voxels
        )

        procs = 4
        parallel = est.estimate_gb(voxels, volumes, n_coeff, procs)
        assert parallel == pytest.approx(
            est.OVERHEAD_GB
            + data
            + est.PARALLEL_COPIES * per_voxel * voxels
            + per_voxel * voxels / procs
            + procs * est.SPAWN_GB_PER_WORKER
        )

    def test_serial_rung_is_cheaper_than_every_parallel_rung(self):
        est = DipyCsdRamEstimator()
        voxels, volumes, n_coeff = 2_000_000, 40, _coeff(8)
        serial = est.estimate_gb(voxels, volumes, n_coeff, 1)
        for procs in (2, 3, 4, 8):
            assert est.estimate_gb(voxels, volumes, n_coeff, procs) > serial

    def test_bottom_rung_is_the_serial_estimate(self):
        est = DipyCsdRamEstimator()
        args = (2_000_000, 40, _coeff(8))
        assert est.bottom_rung_gb(*args) == est.estimate_gb(*args, 1)

    def test_ram_can_be_non_monotone_in_the_worker_count(self):
        """Guards the reason the ladder scans instead of halving.

        Within the parallel branch the parent term is constant in P while the
        worker term falls as 1/P and the spawn term grows linearly, so above a
        volume threshold a large volume at P=2 costs *more* than the same volume
        at P=4. If this ever stops being true the scanning ladder is still
        correct, but its justification changed.
        """
        est = DipyCsdRamEstimator()
        n_coeff = _coeff(8)
        voxels, volumes = _non_monotone_voxels(est, n_coeff), 60
        assert est.estimate_gb(voxels, volumes, n_coeff, 2) > est.estimate_gb(
            voxels, volumes, n_coeff, 4
        )


class TestUntunedCall:
    """``__call__`` prices the node at the worker count the workflow declared."""

    def test_prices_the_declared_worker_count(self, tmp_path):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (64, 64, 30, 41), n_directions=40, num_threads=4)
        mem_gb, debug = est(inputs)
        voxels, volumes = est._shape(inputs)
        assert mem_gb == pytest.approx(
            est.estimate_gb(voxels, volumes, est._n_coeff(inputs), 4)
        )
        assert "untuned" in debug

    def test_undeclared_num_threads_is_priced_as_serial(self, tmp_path):
        est = DipyCsdRamEstimator()
        node = DipyCsdFit()
        node.inputs.in_file = _write_dwi(tmp_path, (32, 32, 20, 31))
        node.inputs.bval, node.inputs.bvec = _write_gradients(tmp_path, 30)
        mem_gb, _ = est(node.inputs)
        voxels, volumes = est._shape(node.inputs)
        assert mem_gb == pytest.approx(
            est.bottom_rung_gb(voxels, volumes, est._n_coeff(node.inputs))
        )


class TestNegotiate:
    """The ladder: largest rung that fits, serial as the floor."""

    def test_ample_budget_keeps_the_declared_worker_count(self, tmp_path):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (64, 64, 30, 41), n_directions=40, num_threads=4)
        plan = est.negotiate(inputs, ram_budget_gb=512.0)
        assert plan.tuned_params == {"num_threads": 4}
        assert plan.n_procs == 4
        assert plan.mem_gb <= 512.0

    def test_never_raises_above_the_declared_count(self, tmp_path):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (32, 32, 20, 31), n_directions=30, num_threads=2)
        plan = est.negotiate(inputs, ram_budget_gb=512.0)
        assert plan.n_procs == 2

    def test_tight_budget_walks_down_to_a_fitting_rung(self, tmp_path):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (144, 144, 60, 65), n_directions=64, num_threads=4)
        voxels, volumes = est._shape(inputs)
        n_coeff = est._n_coeff(inputs)
        # A budget that excludes the declared rung but admits the serial one.
        budget = (
            est.estimate_gb(voxels, volumes, n_coeff, 1)
            + est.estimate_gb(voxels, volumes, n_coeff, 4)
        ) / 2
        plan = est.negotiate(inputs, ram_budget_gb=budget)
        assert plan.mem_gb <= budget
        assert plan.n_procs == plan.tuned_params["num_threads"]
        assert 1 <= plan.n_procs <= 4

    def test_picks_the_largest_fitting_rung_even_when_a_lower_one_does_not_fit(
        self, tmp_path
    ):
        """The scanning ladder's whole point: it must not stop at the first
        rung that fails on the way down."""
        est = DipyCsdRamEstimator()
        n_coeff = _coeff(8)
        # A shape inside the non-monotone regime, so P=2 really is the more
        # expensive rung and a halving ladder really would skip past P=4.
        side = int(round(_non_monotone_voxels(est, n_coeff) ** (1 / 3))) + 1
        inputs = _inputs(
            tmp_path, (side, side, side, 65), n_directions=64, num_threads=4
        )
        voxels, volumes = est._shape(inputs)
        assert est._n_coeff(inputs) == n_coeff
        at4 = est.estimate_gb(voxels, volumes, n_coeff, 4)
        at2 = est.estimate_gb(voxels, volumes, n_coeff, 2)
        assert at2 > at4  # the non-monotone region
        # A budget that admits P=4 but not P=2: halving would land on P=1.
        plan = est.negotiate(inputs, ram_budget_gb=(at4 + at2) / 2)
        assert plan.n_procs == 4

    def test_impossible_budget_returns_the_serial_bottom_rung_and_says_so(
        self, tmp_path
    ):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (144, 144, 60, 65), n_directions=64, num_threads=4)
        voxels, volumes = est._shape(inputs)
        plan = est.negotiate(inputs, ram_budget_gb=0.01)
        assert plan.n_procs == 1
        assert plan.tuned_params == {"num_threads": 1}
        assert plan.mem_gb == pytest.approx(
            est.bottom_rung_gb(voxels, volumes, est._n_coeff(inputs))
        )
        assert "ladder exhausted" in plan.debug_str

    def test_debug_string_reports_the_move(self, tmp_path):
        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (144, 144, 60, 65), n_directions=64, num_threads=4)
        plan = est.negotiate(inputs, ram_budget_gb=0.01)
        for token in ("voxels=", "volumes=", "coeff=", "budget=", "4 -> 1"):
            assert token in plan.debug_str


class TestNodeIntegration:
    """The estimator is usable exactly as the plugin uses it."""

    def test_plan_is_a_ram_plan_with_consistent_cpu_and_tuning(self, tmp_path):
        from swane.patches.nipype_patches import RamPlan

        est = DipyCsdRamEstimator()
        inputs = _inputs(tmp_path, (64, 64, 30, 41), n_directions=40, num_threads=4)
        plan = est.negotiate(inputs, ram_budget_gb=8.0)
        assert isinstance(plan, RamPlan)
        assert plan.n_procs == plan.tuned_params["num_threads"]
        assert plan.mem_gb >= est.MIN_GB

    def test_static_fallback_is_declared_for_the_failed_negotiation_path(self):
        # The workflow sets node._mem_gb from this; the plugin falls back to it
        # when the negotiation cannot run at all.
        assert DipyCsdRamEstimator.STATIC_FALLBACK_GB > 0


# Isolated tree-peak RSS of the real node on the two oracle subjects, measured
# 2026-09-06 with the shipped node code (npeaks=1) at the stated worker count.
# Keyed by (voxels, volumes, n_coeff, workers). The conservative bound must sit
# above every one of them.
ORACLE_PEAKS = {
    # subj1, 256x256x52x16, 15 directions -> lmax 4
    (3_407_872, 16, 15, 4): 2.440,
    # subj2, 144x144x60x65, 64 directions -> lmax 8
    (1_244_160, 65, 45, 4): 2.739,
    (1_244_160, 65, 45, 2): 2.436,
    (1_244_160, 65, 45, 1): 1.316,
}


class TestConservativeBound:
    """The bound is an over-estimate of every measured oracle peak.

    This is the one place the tests pin *measured* figures rather than deriving
    them from the estimator's constants: lowering a multiplier below what covers
    the oracles must fail here. The margins are deliberate -- the estimator's job
    is to keep a RAM-heavy node from being co-scheduled, not to account to the
    megabyte -- but they are bounded on both sides so a wild over-estimate that
    would refuse to schedule the node also fails.
    """

    @pytest.mark.parametrize("key, measured", sorted(ORACLE_PEAKS.items()))
    def test_estimate_covers_the_measured_peak(self, key, measured):
        voxels, volumes, n_coeff, procs = key
        est = DipyCsdRamEstimator()
        assert est.estimate_gb(voxels, volumes, n_coeff, procs) >= measured

    @pytest.mark.parametrize("key, measured", sorted(ORACLE_PEAKS.items()))
    def test_estimate_stays_within_twice_the_measured_peak(self, key, measured):
        voxels, volumes, n_coeff, procs = key
        est = DipyCsdRamEstimator()
        assert est.estimate_gb(voxels, volumes, n_coeff, procs) <= 2.0 * measured

    def test_npeaks_pinning_is_what_the_bound_assumes(self):
        """The per-voxel constant is the ``npeaks=1`` figure the node pins.

        dipy's default would add (5-1) * (24 + 8 + 4 + 8) = 176 B/voxel. If
        :class:`DipyCsdFit` ever stopped pinning ``npeaks=1`` this bound would
        silently under-estimate, so the arithmetic is asserted here.
        """
        est = DipyCsdRamEstimator()
        # gfa 8 + qa 8 + peak_dirs 24 + peak_values 8 + peak_indices 4
        assert est.PEAK_BYTES_PER_VOXEL == 8 + 8 + 24 + 8 + 4
        assert est.per_voxel_bytes(45) == est.PEAK_BYTES_PER_VOXEL + 8 * 45


class TestPluginIntegration:
    """The estimator as the scheduler actually drives it."""

    @staticmethod
    def _node(tmp_path, num_threads=4):
        from nipype.pipeline.engine import Node

        node = Node(DipyCsdFit(), name="dipy_csd", base_dir=str(tmp_path))
        node.inputs.in_file = _write_dwi(tmp_path, (144, 144, 60, 65))
        node.inputs.bval, node.inputs.bvec = _write_gradients(tmp_path, 64)
        node.inputs.mask = _write_dwi(tmp_path, (144, 144, 60), name="mask")
        node.inputs.num_threads = num_threads
        node._mem_gb = DipyCsdRamEstimator.STATIC_FALLBACK_GB
        node.ram_estimator = DipyCsdRamEstimator()
        return node

    @staticmethod
    def _bare_plugin(memory_gb):
        plugin = MonitoredMultiProcPlugin.__new__(MonitoredMultiProcPlugin)
        plugin.memory_gb = memory_gb
        return plugin

    def test_tiny_budget_forces_the_serial_rung_onto_the_node(self, tmp_path):
        node = self._node(tmp_path)
        est = DipyCsdRamEstimator()
        voxels, volumes = est._shape(node.inputs)
        n_coeff = est._n_coeff(node.inputs)

        self._bare_plugin(0.001)._negotiate_ram(node)

        assert node.inputs.num_threads == 1
        assert node.n_procs == 1
        assert node.mem_gb_runtime == pytest.approx(
            est.bottom_rung_gb(voxels, volumes, n_coeff)
        )
        assert node.ram_estimator_str

    def test_ample_budget_leaves_the_declared_worker_count(self, tmp_path):
        node = self._node(tmp_path)
        self._bare_plugin(512.0)._negotiate_ram(node)
        assert node.inputs.num_threads == 4
        assert node.n_procs == 4


# --------------------------------------------------------------------------- #
# Tuned-vs-untuned scientific equivalence (heavy: real dipy CSD on oracle data)
# --------------------------------------------------------------------------- #
ORACLE_DIR = os.environ.get(
    "SWANE_DIPY_ORACLE_DIR",
    os.path.join(
        os.path.expanduser("~"), "test_swane", "dipy_test", "phasee_subj2", "dipy_dti"
    ),
)


def _oracle_inputs():
    """The real subj2 CSD inputs, or ``None`` when the oracle tree is absent."""
    csd_dir = os.path.join(ORACLE_DIR, "dipy_csd")
    bias_dir = os.path.join(ORACLE_DIR, "dipy_bias")
    if not (os.path.isdir(csd_dir) and os.path.isdir(bias_dir)):
        return None
    dwi = sorted(glob.glob(os.path.join(bias_dir, "*.nii.gz")))
    inputs_pklz = os.path.join(csd_dir, "_inputs.pklz")
    if not dwi or not os.path.isfile(inputs_pklz):
        return None
    with gzip.open(inputs_pklz, "rb") as handle:
        recorded = pickle.load(handle)
    return {
        "in_file": dwi[0],
        "bval": recorded["bval"],
        "bvec": recorded["bvec"],
        "mask": recorded["mask"],
    }


@pytest.mark.heavy
class TestTunedEquivalence:
    """Walking the worker count must cost wall-time only, never output.

    The premise of E2d is that ``peaks_from_model``'s ``num_processes`` is a
    pure scheduling knob: dipy chunks strictly by voxel index and reassembles by
    the same index, every worker runs the identical serial per-voxel fit, and
    :class:`DipyCsdFit` pins BLAS to one thread before the pool starts so the
    arithmetic is thread-count-independent on both sides. This runs the node
    twice on the **real oracle DWI** -- once at the declared top rung (4 worker
    processes, the parallel branch) and once after the *real* plugin negotiation
    has forced the bottom rung (1 process, the serial branch) -- and demands a
    bit-for-bit identical ``shm_coeff``, the node's only output.

    The mask is narrowed to a few axial slices so the two fits finish in
    minutes rather than an hour. The property under test is per-voxel, so it
    does not depend on how many voxels are fitted; the input, gradient table and
    response fit are the real ones.
    """

    SLICES = 3

    def test_serial_and_parallel_shm_coeff_are_identical(self, tmp_path):
        from nipype.pipeline.engine import Node

        oracle = _oracle_inputs()
        if oracle is None:
            pytest.skip(f"dipy oracle inputs not found under {ORACLE_DIR}")

        # Narrow the real mask to a central slab; everything else stays real.
        mask_img = nib.load(oracle["mask"])
        mask = np.asanyarray(mask_img.dataobj) > 0
        slab = np.zeros_like(mask)
        mid = mask.shape[2] // 2
        lo, hi = mid - self.SLICES // 2, mid - self.SLICES // 2 + self.SLICES
        slab[:, :, lo:hi] = mask[:, :, lo:hi]
        assert slab.sum() > 0, "the oracle mask is empty in the central slab"
        slab_path = str(tmp_path / "mask_slab.nii.gz")
        nib.save(
            nib.Nifti1Image(slab.astype(np.uint8), mask_img.affine, mask_img.header),
            slab_path,
        )

        def _build(name, base):
            node = Node(DipyCsdFit(), name=name, base_dir=str(base))
            node.inputs.in_file = oracle["in_file"]
            node.inputs.bval = oracle["bval"]
            node.inputs.bvec = oracle["bvec"]
            node.inputs.mask = slab_path
            node.inputs.num_threads = 4
            node._mem_gb = DipyCsdRamEstimator.STATIC_FALLBACK_GB
            node.ram_estimator = DipyCsdRamEstimator()
            return node

        top = _build("csd_top", tmp_path / "top")
        assert top.inputs.num_threads == 4  # the parallel branch
        top.run()

        bottom = _build("csd_bottom", tmp_path / "bottom")
        TestPluginIntegration._bare_plugin(0.001)._negotiate_ram(bottom)
        assert bottom.inputs.num_threads == 1  # the serial branch
        bottom.run()

        parallel = nib.load(top.result.outputs.shm_coeff).get_fdata()
        serial = nib.load(bottom.result.outputs.shm_coeff).get_fdata()
        assert parallel.shape == serial.shape
        assert np.array_equal(parallel, serial)
