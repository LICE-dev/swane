"""Ladder/negotiation tests for
:class:`swane.nipype_pipeline.interfaces.ram_estimators.DipyTrackingRamEstimator`.

``DipyTracking`` runs probabilistic tractography over a brain-cropped SH volume.
After the Phase-1bis crop + float32 + streaming-``.trx`` fixes, its RAM has an
**incompressible parent term** -- the working set that scales with the field of
view (voxels) -- plus two genuinely quality-neutral levers the estimator may
walk to fit the RAM budget:

* ``seed_buffer_fraction`` -- the fraction of the seed pool
  ``probabilistic_tracking`` buffers per streaming chunk. Superseding the node's
  hardcoded 0.7 compromise, the estimator walks it over ``[0.3, 1.0]``: up to
  dipy's 1.0 when budget is ample, down to a 0.3 floor under pressure (user
  decision, 2026-09-06);
* ``trx_chunk_size`` -- the streamline write-chunk, walked down toward 1000 only
  after the buffer floor is reached.

Both are bit-for-bit quality-neutral at any rung (the heavy tuned-vs-untuned test
proves it); only wall time / peak RSS changes. The parent term is priced from the
``nodif_brain`` foreground bounding box -- the same crop the node applies, which is
what the peak tracks -- while the seed count, which sizes the buffer lever, is read
from the WM PVE mask at the same volume density the node seeds at, so a coarse
acquisition is priced for the larger seed pool it gets.

These tests are deliberately **coefficient-agnostic**: every expected budget is
derived from the estimator's own model, so they keep their meaning if the
conservative constants are retuned.
"""

import numpy as np
import nibabel as nib
import pytest
from nipype.pipeline.engine import Node

from swane.nipype_pipeline.interfaces.dipy.DipyTracking import (
    DipyTracking,
    wm_seed_mask,
    seed_count_for_volume,
    REFERENCE_VOXEL_MM3,
)
from swane.nipype_pipeline.interfaces.ram_estimators import DipyTrackingRamEstimator
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)

SH_SHAPE = (24, 24, 20, 15)  # spatial 11520 voxels, 15 SH coeffs
WM_VOXELS = 1500


def _write_shm(tmp_path, shape=SH_SHAPE, name="shm"):
    """Write a zero SH volume; only the header (shape) matters to the parent
    term, so uint8 zeros are enough and stay cheap."""
    path = str(tmp_path / f"{name}.nii.gz")
    nib.save(nib.Nifti1Image(np.zeros(shape, dtype=np.uint8), np.eye(4)), path)
    return path


def _write_pve(tmp_path, wm_voxels=WM_VOXELS, shape=SH_SHAPE[:3], name="pve"):
    """Write a WM PVE map with exactly ``wm_voxels`` seed-eligible voxels
    (value 1.0 >= the 0.5 seed threshold), the rest zero."""
    data = np.zeros(shape, dtype=np.float32)
    flat = data.reshape(-1)
    flat[:wm_voxels] = 1.0
    path = str(tmp_path / f"{name}.nii.gz")
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return path


def _write_nodif(tmp_path, shape=SH_SHAPE[:3], name="nodif"):
    """A skull-stripped b0 that is foreground over the whole volume, so the
    estimator's nodif_brain bounding-box crop equals the full shape -- keeping the
    cropped-brain voxel count equal to ``_dims()`` for the coefficient-agnostic
    assertions below."""
    path = str(tmp_path / f"{name}.nii.gz")
    nib.save(nib.Nifti1Image(np.ones(shape, dtype=np.uint8), np.eye(4)), path)
    return path


def _inputs(tmp_path, seed_density=2, num_threads=4, trx_chunk_size=10000):
    interface = DipyTracking()
    interface.inputs.shm_coeff = _write_shm(tmp_path)
    interface.inputs.pve_wm = _write_pve(tmp_path)
    interface.inputs.nodif_brain = _write_nodif(tmp_path)
    interface.inputs.seed_density = seed_density
    interface.inputs.num_threads = num_threads
    interface.inputs.trx_chunk_size = trx_chunk_size
    return interface.inputs


def _dims():
    voxels = int(np.prod(SH_SHAPE[:3]))
    return voxels


def _bare_plugin(memory_gb):
    plugin = MonitoredMultiProcPlugin.__new__(MonitoredMultiProcPlugin)
    plugin.memory_gb = memory_gb
    return plugin


class TestModel:
    def test_estimate_grows_with_voxels_seeds_buffer_and_chunk(self):
        est = DipyTrackingRamEstimator()
        base = est.estimate_gb(voxels=100_000, seeds=200_000, buffer=0.5, chunk=5000)
        assert est.estimate_gb(200_000, 200_000, 0.5, 5000) > base
        assert est.estimate_gb(100_000, 400_000, 0.5, 5000) > base
        assert est.estimate_gb(100_000, 200_000, 0.9, 5000) > base
        assert est.estimate_gb(100_000, 200_000, 0.5, 9000) > base

    def test_seed_count_is_the_volume_density_the_node_seeds_at(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, seed_density=3)
        pve = nib.load(inputs.pve_wm)
        expected = seed_count_for_volume(wm_seed_mask(pve.get_fdata()), pve.affine, 3)
        assert est._seed_count(inputs) == expected
        # the fixture's affine is 1 mm3 per voxel, so the masked volume in mm3
        # is the WM voxel count
        assert expected == round(WM_VOXELS * 3 / REFERENCE_VOXEL_MM3)

    def test_seed_count_grows_with_the_voxel_size(self, tmp_path):
        """A coarser grid holding the same white matter is seeded just as
        densely per mm3, so the pool the buffer lever scales does not shrink --
        the estimator must price that, not the voxel count."""
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, seed_density=2)
        fine = est._seed_count(inputs)

        pve = nib.load(inputs.pve_wm)
        coarse_path = str(tmp_path / "pve_coarse.nii.gz")
        nib.save(
            nib.Nifti1Image(
                pve.get_fdata().astype(np.float32), np.diag([2.0, 2.0, 2.0, 1.0])
            ),
            coarse_path,
        )
        inputs.pve_wm = coarse_path
        # eight times the voxel volume, eight times the seeds -- up to the
        # rounding of a fractional seed count
        assert est._seed_count(inputs) == pytest.approx(8 * fine, rel=1e-3)

    def test_bottom_rung_is_min_buffer_and_min_chunk(self):
        est = DipyTrackingRamEstimator()
        vox, seeds = 100_000, 200_000
        assert est.bottom_rung_gb(vox, seeds) == pytest.approx(
            est.estimate_gb(vox, seeds, est.BUFFER_MIN, est.CHUNK_MIN)
        )


class TestLadder:
    def test_ample_budget_supersedes_to_max_buffer_and_declared_chunk(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, trx_chunk_size=10000)
        vox = _dims()
        seeds = est._seed_count(inputs)

        plan = est.negotiate(
            inputs, ram_budget_gb=est.estimate_gb(vox, seeds, 1.0, 10000) * 4
        )

        assert plan.tuned_params["seed_buffer_fraction"] == est.BUFFER_MAX
        assert plan.tuned_params["trx_chunk_size"] == 10000
        assert plan.n_procs is None  # E2b does not tune threads
        assert plan.mem_gb == pytest.approx(est.estimate_gb(vox, seeds, 1.0, 10000))

    def test_tight_budget_steps_the_buffer_down_first(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, trx_chunk_size=10000)
        vox = _dims()
        seeds = est._seed_count(inputs)

        # A budget between full-buffer and half-buffer (chunk left at declared).
        full = est.estimate_gb(vox, seeds, 1.0, 10000)
        half = est.estimate_gb(vox, seeds, 0.5, 10000)
        assert full > half
        budget = (full + half) / 2

        plan = est.negotiate(inputs, ram_budget_gb=budget)

        assert (
            est.BUFFER_MIN < plan.tuned_params["seed_buffer_fraction"] < est.BUFFER_MAX
        )
        assert plan.tuned_params["trx_chunk_size"] == 10000  # chunk untouched yet
        assert plan.mem_gb <= budget

    def test_chunk_only_drops_after_the_buffer_floor(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, trx_chunk_size=10000)
        vox = _dims()
        seeds = est._seed_count(inputs)

        # A budget the min buffer alone cannot meet at the full chunk, but a
        # smaller chunk can: the ladder must pin buffer=MIN and walk the chunk.
        target_chunk = 4000
        budget = est.estimate_gb(vox, seeds, est.BUFFER_MIN, target_chunk)
        assert budget < est.estimate_gb(vox, seeds, est.BUFFER_MIN, 10000)

        plan = est.negotiate(inputs, ram_budget_gb=budget)

        assert plan.tuned_params["seed_buffer_fraction"] == est.BUFFER_MIN
        assert est.CHUNK_MIN <= plan.tuned_params["trx_chunk_size"] < 10000
        assert plan.mem_gb <= budget

    def test_impossible_budget_returns_the_bottom_rung_and_says_so(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path)
        vox = _dims()
        seeds = est._seed_count(inputs)

        plan = est.negotiate(inputs, ram_budget_gb=0.001)

        assert plan.tuned_params["seed_buffer_fraction"] == est.BUFFER_MIN
        assert plan.tuned_params["trx_chunk_size"] == est.CHUNK_MIN
        assert plan.mem_gb == pytest.approx(est.bottom_rung_gb(vox, seeds))
        assert "bottom" in plan.debug_str.lower()

    def test_buffer_never_exceeds_max_and_chunk_never_exceeds_declared(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, trx_chunk_size=6000)
        vox = _dims()
        seeds = est._seed_count(inputs)

        plan = est.negotiate(
            inputs, ram_budget_gb=est.estimate_gb(vox, seeds, 1.0, 6000) * 10
        )

        assert plan.tuned_params["seed_buffer_fraction"] == est.BUFFER_MAX
        assert plan.tuned_params["trx_chunk_size"] == 6000  # declared cap, not 10000

    def test_debug_string_reports_voxels_seeds_and_the_rung(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path)
        vox = _dims()
        seeds = est._seed_count(inputs)

        plan = est.negotiate(
            inputs, ram_budget_gb=est.estimate_gb(vox, seeds, 1.0, 10000)
        )

        assert str(vox) in plan.debug_str
        assert str(seeds) in plan.debug_str
        assert "buffer" in plan.debug_str.lower()


class TestOneWayCall:
    def test_call_prices_the_top_rung(self, tmp_path):
        est = DipyTrackingRamEstimator()
        inputs = _inputs(tmp_path, trx_chunk_size=8000)
        vox = _dims()
        seeds = est._seed_count(inputs)

        mem_gb, debug = est(inputs)

        assert mem_gb == pytest.approx(est.estimate_gb(vox, seeds, 1.0, 8000))
        assert debug


class TestPluginIntegration:
    def _node(self, tmp_path):
        node = Node(DipyTracking(), name="tracking", base_dir=str(tmp_path))
        node.inputs.shm_coeff = _write_shm(tmp_path)
        node.inputs.pve_wm = _write_pve(tmp_path)
        node.inputs.nodif_brain = _write_nodif(tmp_path)
        node.inputs.seed_density = 2
        node.inputs.num_threads = 4
        node.ram_estimator = DipyTrackingRamEstimator()
        return node

    def test_tuned_levers_reach_the_node_inputs(self, tmp_path):
        node = self._node(tmp_path)

        _bare_plugin(0.001)._negotiate_ram(node)

        est = DipyTrackingRamEstimator()
        assert node.inputs.seed_buffer_fraction == est.BUFFER_MIN
        assert node.inputs.trx_chunk_size == est.CHUNK_MIN

    def test_n_procs_is_left_untouched(self, tmp_path):
        node = self._node(tmp_path)
        assert node.n_procs == 4  # derived from num_threads

        _bare_plugin(0.001)._negotiate_ram(node)

        assert node.n_procs == 4  # E2b does not tune threads

    def test_negotiated_reservation_lands_on_the_node(self, tmp_path):
        node = self._node(tmp_path)
        est = DipyTrackingRamEstimator()
        vox = _dims()
        seeds = est._seed_count(node.inputs)

        _bare_plugin(0.001)._negotiate_ram(node)

        assert node.mem_gb_runtime == pytest.approx(est.bottom_rung_gb(vox, seeds))
        assert node.ram_estimator_str


# --------------------------------------------------------------------------- #
# Tuned-vs-untuned scientific equivalence (heavy: real dipy tractography)
# --------------------------------------------------------------------------- #
@pytest.mark.heavy
class TestTunedEquivalence:
    """Walking the levers must cost wall-time only, never scientific output.

    The whole premise of E2b is that ``seed_buffer_fraction`` and
    ``trx_chunk_size`` are pure scheduling knobs: seeds are consumed in a fixed
    order and each streamline's trajectory is a function of its seed coordinate
    and ``random_seed`` alone. This runs the node twice on the same input --
    once at the top rung (buffer=1.0, chunk=10000) and once after the *real*
    plugin negotiation has forced the bottom rung (buffer=0.3, chunk=1000) --
    and demands an identical set of streamline trajectories, with the BLAS/OMP
    thread environment matched (num_threads=1) on both sides so only the levers
    can differ. Streamline *order* may vary, so the comparison is order-invariant.
    """

    def test_bottom_rung_streamlines_are_identical(self, tmp_path):
        import os
        from dipy.io.streamline import load_tractogram
        from nipype.pipeline.engine import Node

        from swane.tests.nipype_pipeline.interfaces.dipy.test_dipy_tracking import (
            _pve_maps,
            _sh_field,
            _fa_field,
            _nodif_brain_from_pve,
        )

        affine = np.eye(4)
        wm, gm, csf = _pve_maps()

        def _nii(name, data):
            path = str(tmp_path / name)
            nib.save(nib.Nifti1Image(data, affine), path)
            return path

        diff2ref = str(tmp_path / "eq_diff2ref.txt")
        np.savetxt(diff2ref, np.eye(4))
        inputs = {
            "shm_coeff": _nii("eq_sh.nii.gz", _sh_field()),
            "pve_wm": _nii("eq_wm.nii.gz", wm),
            "fa": _nii("eq_fa.nii.gz", _fa_field(wm)),
            "nodif_brain": _nii("eq_nb.nii.gz", _nodif_brain_from_pve(wm, gm, csf)),
            "reference": _nii("eq_ref.nii.gz", np.zeros(wm.shape, dtype=np.float32)),
            "affine_diff2ref": diff2ref,
        }

        def _canonical(streamlines):
            return sorted(tuple(np.round(s.ravel(), 2)) for s in streamlines)

        def _node(work, **overrides):
            node = Node(DipyTracking(), name="tracking", base_dir=work)
            for key, value in inputs.items():
                setattr(node.inputs, key, value)
            node.inputs.num_threads = 1
            node.inputs.random_seed = 1
            node.inputs.seed_density = 2
            for key, value in overrides.items():
                setattr(node.inputs, key, value)
            return node

        saved = {
            var: os.environ.get(var)
            for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        }
        for var in saved:
            os.environ[var] = "1"
        try:
            top_node = _node(
                str(tmp_path / "top"),
                seed_buffer_fraction=1.0,
                trx_chunk_size=10000,
            )
            top_out = top_node.run().outputs

            bottom_node = _node(str(tmp_path / "bottom"))
            bottom_node.ram_estimator = DipyTrackingRamEstimator()
            _bare_plugin(0.001)._negotiate_ram(bottom_node)
            # The negotiation must really have moved both levers to the floor,
            # or the comparison below would be vacuous.
            assert bottom_node.inputs.seed_buffer_fraction == 0.3
            assert bottom_node.inputs.trx_chunk_size == 1000
            bottom_out = bottom_node.run().outputs
        finally:
            for var, val in saved.items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val

        top = _canonical(
            load_tractogram(
                top_out.tractogram, "same", bbox_valid_check=False
            ).streamlines
        )
        bottom = _canonical(
            load_tractogram(
                bottom_out.tractogram, "same", bbox_valid_check=False
            ).streamlines
        )

        assert len(top) > 0
        assert top == bottom, "tuning the RAM levers changed the tractogram"
