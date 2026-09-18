"""Unit tests for the bidirectional RAM estimator (Phase 2, Task E1).

The one-way :class:`~nipype.utils.ram_estimator.RamEstimator` (``__call__`` ->
``(mem_gb, debug_str)``) is extended with a negotiation entry point,
``negotiate(inputs, ram_budget_gb) -> RamPlan``, that both reserves RAM and
tunes a node's quality-neutral parameters so its estimated peak fits the RAM
budget the host is allowed to use.

Task E1 covers:

* the ``RamPlan`` container and the default ``negotiate`` (wraps ``__call__``,
  empty tuning) — so the FSL estimators keep identical behaviour;
* the SWANe-side plugin hook in
  :class:`~swane.nipype_pipeline.engine.MonitoredMultiProcPlugin.MonitoredMultiProcPlugin`
  that negotiates the plan, applies the tuned parameters, and records the
  reservation, CPU count and debug trace on the node.

The tests exercise pure-Python arithmetic against tiny synthetic NIfTI volumes
generated with nibabel/numpy, so no FSL/FreeSurfer installation is needed.
"""

import numpy as np
import nibabel as nib
import pytest
from nipype import Node
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    File,
    traits,
)

from nipype.utils.ram_estimator import RamEstimator

# RamPlan and the default RamEstimator.negotiate live in SWANe (a nipype
# monkeypatch), so the installed nipype stays official/untouched. Importing the
# patch module applies the patch that adds RamEstimator.negotiate.
from swane.patches.nipype_patches import RamPlan
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)
from swane.nipype_pipeline.interfaces.ram_estimators import FlirtRamEstimator


def _tiny_image(tmp_path, name="small.nii.gz"):
    data = np.zeros((3, 3, 3), dtype=np.uint8)
    path = str(tmp_path / name)
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    return path


class _FlirtInputs(BaseInterfaceInputSpec):
    in_file = File(exists=False)
    reference = File(exists=False)


class _TunableInputs(BaseInterfaceInputSpec):
    in_file = File(exists=False)
    num_threads = traits.Int(4, usedefault=True)


class _TunableInterface(BaseInterface):
    """Minimal interface exposing a tunable ``num_threads`` trait."""

    input_spec = _TunableInputs

    def _run_interface(self, runtime):  # pragma: no cover - never executed here
        return runtime


class _StubTunableEstimator(RamEstimator):
    """Tunable estimator that lowers threads and reserves RAM/CPU to match."""

    def __init__(self):
        super().__init__(input_multipliers={"in_file": 1}, overhead_gb=0.3)

    def negotiate(self, inputs, ram_budget_gb):
        # Deterministic: drop threads to 2, reserve accordingly.
        return RamPlan(
            mem_gb=1.5,
            tuned_params={"num_threads": 2},
            n_procs=2,
            debug_str="stub: threads 4 -> 2",
        )


class _RaisingEstimator(RamEstimator):
    """Estimator whose negotiate always fails (fail-safe path)."""

    def negotiate(self, inputs, ram_budget_gb):
        raise RuntimeError("boom")


def _bare_plugin(memory_gb):
    """A plugin instance without the heavy MultiProc __init__ (no pool)."""
    plugin = MonitoredMultiProcPlugin.__new__(MonitoredMultiProcPlugin)
    plugin.memory_gb = memory_gb
    return plugin


class TestDefaultNegotiate:
    """A non-tunable estimator negotiates exactly like the one-way call."""

    def test_negotiate_is_monkeypatched_onto_the_nipype_base(self):
        """The default negotiate is added to the installed nipype base class.

        SWANe must not modify the installed nipype, so ``negotiate`` is a
        SWANe-owned monkeypatch on ``RamEstimator`` rather than an edit to the
        nipype source. Importing the patch module applies it.
        """
        assert hasattr(RamEstimator, "negotiate")

    def test_negotiate_wraps_call_with_empty_tuning(self, tmp_path):
        path = _tiny_image(tmp_path)
        inputs = _FlirtInputs()
        inputs.in_file = path
        inputs.reference = path

        est = FlirtRamEstimator()
        mem_gb, debug = est(inputs)

        plan = est.negotiate(inputs, ram_budget_gb=8.0)

        assert isinstance(plan, RamPlan)
        assert plan.mem_gb == mem_gb
        assert plan.tuned_params == {}
        assert plan.n_procs is None
        assert plan.debug_str == debug


class TestPluginNegotiationHook:
    """The plugin hook negotiates, applies tuning, and records the plan."""

    def test_backcompat_fsl_estimator_matches_one_way(self, tmp_path):
        """A node with FlirtRamEstimator yields the same mem_gb, empty tuning."""
        path = _tiny_image(tmp_path)

        # Reference: the untouched one-way reservation.
        ref = Node(_TunableInterface(), name="ref")
        ref.inputs.in_file = path
        ref.ram_estimator = FlirtRamEstimator()
        one_way_mem = ref.mem_gb_runtime

        node = Node(_TunableInterface(), name="n")
        node.inputs.in_file = path
        node.ram_estimator = FlirtRamEstimator()

        _bare_plugin(8.0)._negotiate_ram(node)

        assert node.mem_gb_runtime == one_way_mem
        assert node._ram_estimated is True
        # No tunable params on the FSL estimator -> num_threads untouched.
        assert node.inputs.num_threads == 4

    def test_tunable_estimator_applies_params_and_nprocs(self, tmp_path):
        path = _tiny_image(tmp_path)
        node = Node(_TunableInterface(), name="n")
        node.inputs.in_file = path
        node.ram_estimator = _StubTunableEstimator()

        _bare_plugin(8.0)._negotiate_ram(node)

        assert node.inputs.num_threads == 2
        assert node.n_procs == 2
        assert node.mem_gb_runtime == pytest.approx(1.5)
        assert node.ram_estimator_str == "stub: threads 4 -> 2"

    def test_failsafe_keeps_static_mem_gb(self, tmp_path):
        path = _tiny_image(tmp_path)
        node = Node(_TunableInterface(), name="n", mem_gb=2.75)
        node.inputs.in_file = path
        node.ram_estimator = _RaisingEstimator()

        _bare_plugin(8.0)._negotiate_ram(node)

        # Static reservation preserved, no tuning, no re-run of the estimator.
        assert node.mem_gb_runtime == pytest.approx(2.75)
        assert node.inputs.num_threads == 4
        assert node._ram_estimated is True
