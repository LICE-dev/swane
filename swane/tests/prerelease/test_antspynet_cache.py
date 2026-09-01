"""The weight pre-cache must not load TensorFlow into its caller.

``run_sweep`` calls the pre-cache once and then lives for the whole sweep --
hours -- forking a process per pass. Importing antspynet in that process leaves
TensorFlow resident (~700 MB measured) for the entire run, and every forked
pass inherits that footprint. On a memory-tight host it is enough to push
antspyx/ITK nodes (N4 bias correction) into swap or an outright crash, so the
fetch has to happen in a short-lived child process instead.
"""

import sys

import pytest

from swane.config.config_enums import DeskullModality
from swane.tests.prerelease import antspynet_cache


def test_weight_names_cover_every_modality_without_duplicates():
    names = antspynet_cache.antspynet_weights()
    # BOLD and NODIF share the "bold" network: asked for once, not twice.
    assert len(names) == len(set(names))
    assert set(names) == {
        antspynet_cache.WEIGHTS_BY_MODALITY[m.value] for m in DeskullModality
    }


def test_preload_runs_in_a_child_process_and_leaves_the_caller_clean(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _Done:
            returncode = 0

        return _Done()

    monkeypatch.setattr(antspynet_cache.subprocess, "run", fake_run)
    antspynet_cache.preload_antspynet_models(verbose=False)

    assert calls, "the pre-cache must shell out, not import antspynet in-process"
    assert calls[0][0] == sys.executable
    assert "antspynet" not in sys.modules, (
        "importing antspynet in the caller leaves TensorFlow resident for the "
        "whole sweep"
    )
