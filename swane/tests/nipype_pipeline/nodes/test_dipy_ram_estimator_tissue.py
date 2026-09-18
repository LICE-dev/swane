"""Tests for
:class:`swane.nipype_pipeline.nodes.ram_estimators.DipyTissueRamEstimator`.

``DipyTissueClassifier`` runs dipy's ``TissueClassifierHMRF.classify`` on the
T1 ``reference_brain`` to derive the three PVE maps. Unlike motion, tracking and
CSD, it has **no quality-neutral lever**: the node already pins
``OMP_NUM_THREADS=1`` internally and exposes no thread/worker trait, and the
HMRF classify is a serial Python/numpy loop. Peak RSS is **byte-identical
across threads**, so a thread lever would
tune nothing. This estimator is therefore a **classic one-way** ``RamEstimator``
(like the FSL ones): it reserves RAM and tunes nothing, inheriting the default
``negotiate`` (empty ``tuned_params``, ``n_procs=None``).

The same probes showed peak RSS is **linear in the T1 voxel count**
(``~260 B/voxel + 0.36 GB`` over 2.0-20.5 Mvoxel), with the real-node peaks
sitting below that line. The estimator's bound (``280 B/voxel + 0.4 GB``,
``max_gb=None``) is a deliberate conservative over-estimate of that fit, covering
every measured point (see ``docs/superpowers/`` E2c note).

Where they can be, these tests are **coefficient-agnostic**: expected figures are
derived from the estimator's own constants, so they keep their meaning if the
bound is retuned. The one exception is the conservative-bound guard, which pins
the two *measured* oracle peaks on purpose -- lowering the multiplier below what
covers the oracles must fail.
"""

import numpy as np
import nibabel as nib
import pytest
from nipype.pipeline.engine import Node

from swane.nipype_pipeline.nodes.DipyTissueClassifier import DipyTissueClassifier
from swane.nipype_pipeline.nodes.ram_estimators import DipyTissueRamEstimator

# Importing the plugin applies the SWANe nipype patches, which add the default
# RamEstimator.negotiate this estimator inherits.
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)

# Representative benchmark points; the conservative bound must sit above both.
ORACLE_PEAKS = {
    (224, 256, 170): 2.569,  # 9_748_480 voxels
    (320, 320, 200): 5.160,  # 20_480_000 voxels
}


def _write_t1(tmp_path, shape, name="t1_brain"):
    """Write a zero-filled 3D T1 brain; return its path.

    Only the header (shape) matters to the estimator -- it counts spatial
    voxels and never reads the data -- so uint8 zeros stay cheap.
    """
    data = np.zeros(shape, dtype=np.uint8)
    path = str(tmp_path / f"{name}.nii.gz")
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return path


def _inputs(tmp_path, shape, name="t1_brain"):
    interface = DipyTissueClassifier()
    interface.inputs.in_file = _write_t1(tmp_path, shape, name=name)
    return interface.inputs


def _voxels(shape):
    return int(np.prod(shape[:3]))


def _expected_gb(est, shape):
    """The estimate the estimator's own constants imply for ``shape``."""
    raw = _voxels(shape) * est.BYTES_PER_VOXEL / 1024**3 + est.OVERHEAD_GB
    return max(est.MIN_GB, raw)


def _bare_plugin(memory_gb):
    """A plugin instance without the heavy MultiProc ``__init__`` (no pool)."""
    plugin = MonitoredMultiProcPlugin.__new__(MonitoredMultiProcPlugin)
    plugin.memory_gb = memory_gb
    return plugin


class TestModel:
    """The estimate tracks the T1 voxel count and nothing else."""

    def test_estimate_grows_with_input_voxels(self, tmp_path):
        est = DipyTissueRamEstimator()
        small, _ = est(_inputs(tmp_path, (128, 128, 80), name="small"))
        big, _ = est(_inputs(tmp_path, (256, 256, 160), name="big"))
        assert big > small

    def test_estimate_matches_the_voxel_multiplier_formula(self, tmp_path):
        """Coefficient-agnostic: voxels * B/voxel / 2**30 + overhead."""
        est = DipyTissueRamEstimator()
        shape = (200, 200, 100)  # 4.0 Mvoxel, comfortably above the min floor
        mem_gb, debug = est(_inputs(tmp_path, shape))
        assert mem_gb == pytest.approx(_expected_gb(est, shape))
        assert debug

    def test_tiny_input_respects_the_min_floor(self, tmp_path):
        est = DipyTissueRamEstimator()
        mem_gb, _ = est(_inputs(tmp_path, (10, 10, 10)))
        assert mem_gb == pytest.approx(est.MIN_GB)


class TestConservativeBound:
    """The bound must over-estimate the real node on the oracle inputs."""

    @pytest.mark.parametrize("shape,measured", ORACLE_PEAKS.items())
    def test_estimate_exceeds_the_measured_oracle_peak(self, tmp_path, shape, measured):
        est = DipyTissueRamEstimator()
        mem_gb, _ = est(_inputs(tmp_path, shape))
        assert mem_gb > measured

    def test_large_input_is_not_clamped_down(self, tmp_path):
        """max_gb is None: a big T1 must reserve its full modelled peak.

        Clamping the estimate down would make the node under-reserve and let the
        scheduler co-admit other heavy work -- the exact failure the estimator
        exists to prevent. Deciding a node cannot fit is the scheduler's job.
        """
        est = DipyTissueRamEstimator()
        assert est.max_gb is None
        shape = (400, 400, 200)  # 32 Mvoxel -> modelled well above the old 8 GB cap
        mem_gb, _ = est(_inputs(tmp_path, shape))
        assert mem_gb == pytest.approx(_expected_gb(est, shape))
        assert mem_gb > 8


class TestClassicNegotiation:
    """No lever: the inherited negotiate reserves RAM and tunes nothing."""

    def test_negotiate_returns_the_call_estimate_with_empty_tuning(self, tmp_path):
        est = DipyTissueRamEstimator()
        inputs = _inputs(tmp_path, (200, 200, 100))
        mem_gb, _ = est(inputs)

        plan = est.negotiate(inputs, ram_budget_gb=0.001)

        assert plan.tuned_params == {}
        assert plan.n_procs is None
        assert plan.mem_gb == pytest.approx(mem_gb)

    def test_a_tight_budget_does_not_shrink_the_estimate(self, tmp_path):
        """A classic estimator ignores the budget -- there is nothing to tune."""
        est = DipyTissueRamEstimator()
        inputs = _inputs(tmp_path, (256, 256, 160))
        ample = est.negotiate(inputs, ram_budget_gb=1000).mem_gb
        tight = est.negotiate(inputs, ram_budget_gb=0.001).mem_gb
        assert tight == pytest.approx(ample)


class TestPluginIntegration:
    """Through the real plugin the node is reserved but never mutated."""

    def _node(self, tmp_path, shape=(200, 200, 100)):
        node = Node(DipyTissueClassifier(), name="dipy_tissue", base_dir=str(tmp_path))
        node.inputs.in_file = _write_t1(tmp_path, shape)
        node._mem_gb = DipyTissueRamEstimator.STATIC_FALLBACK_GB
        node.n_procs = 1
        node.ram_estimator = DipyTissueRamEstimator()
        return node

    def test_reservation_lands_on_the_node_without_tuning(self, tmp_path):
        node = self._node(tmp_path)
        est = DipyTissueRamEstimator()
        in_file_before = node.inputs.in_file

        _bare_plugin(0.001)._negotiate_ram(node)

        assert node.mem_gb_runtime == pytest.approx(est(node.inputs)[0])
        assert node.n_procs == 1  # unchanged: n_procs=None keeps the declared value
        assert node.inputs.in_file == in_file_before  # inputs untouched
        assert node.ram_estimator_str

    def test_node_has_no_thread_lever_to_tune(self, tmp_path):
        """Guard the premise: the node exposes no thread/worker trait to tune."""
        node = self._node(tmp_path)
        traits = node.inputs.traits()
        assert "num_threads" not in traits
        assert "n_procs" not in traits
