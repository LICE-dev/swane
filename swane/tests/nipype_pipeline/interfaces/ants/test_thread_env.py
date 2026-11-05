"""Unit tests for :func:`swane.nipype_pipeline.interfaces.ants.thread_env`, the
single place where ITK-based interfaces export their thread count."""

import os

import pytest
from nipype.interfaces.base import Undefined

from swane.nipype_pipeline.interfaces.ants import ITK_THREADS_VAR, thread_env

OTHER_VAR = "SWANE_TEST_THREADS"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ITK_THREADS_VAR, raising=False)
    monkeypatch.delenv(OTHER_VAR, raising=False)


def test_exports_the_itk_variable_by_default():
    with thread_env(3):
        assert os.environ[ITK_THREADS_VAR] == "3"
    assert ITK_THREADS_VAR not in os.environ


def test_exports_every_requested_variable():
    with thread_env(2, (ITK_THREADS_VAR, OTHER_VAR)):
        assert os.environ[ITK_THREADS_VAR] == "2"
        assert os.environ[OTHER_VAR] == "2"
    assert ITK_THREADS_VAR not in os.environ
    assert OTHER_VAR not in os.environ


def test_restores_a_previous_value(monkeypatch):
    monkeypatch.setenv(ITK_THREADS_VAR, "7")
    with thread_env(1):
        assert os.environ[ITK_THREADS_VAR] == "1"
    assert os.environ[ITK_THREADS_VAR] == "7"


def test_restores_even_when_the_block_raises():
    with pytest.raises(RuntimeError):
        with thread_env(4):
            raise RuntimeError("boom")
    assert ITK_THREADS_VAR not in os.environ


@pytest.mark.parametrize("num_threads", [Undefined, 0, -1])
def test_leaves_the_environment_alone_without_a_positive_count(
    monkeypatch, num_threads
):
    """Undefined or <=0 means "library default": exporting 0 would be
    undefined for OpenMP, so nothing is exported and nothing is changed."""
    monkeypatch.setenv(OTHER_VAR, "5")
    with thread_env(num_threads, (ITK_THREADS_VAR, OTHER_VAR)):
        assert ITK_THREADS_VAR not in os.environ
        assert os.environ[OTHER_VAR] == "5"
    assert os.environ[OTHER_VAR] == "5"


@pytest.mark.parametrize(
    "module, name",
    [
        (
            "swane.nipype_pipeline.interfaces.ants.AntsApplyTransforms",
            "AntsApplyTransforms",
        ),
        ("swane.nipype_pipeline.interfaces.ants.AntsAtropos", "AntsAtropos"),
        (
            "swane.nipype_pipeline.interfaces.ants.AntsComposeTransform",
            "AntsComposeTransform",
        ),
        (
            "swane.nipype_pipeline.interfaces.ants.AntsN4BiasFieldCorrection",
            "AntsN4BiasFieldCorrection",
        ),
        (
            "swane.nipype_pipeline.interfaces.ants.AntsPyNetBrainExtraction",
            "AntsPyNetBrainExtraction",
        ),
        ("swane.nipype_pipeline.interfaces.ants.AntsRegistration", "AntsRegistration"),
        ("swane.nipype_pipeline.interfaces.dti.DwiBiasCorrection", "DwiBiasCorrection"),
    ],
)
def test_every_in_process_itk_interface_runs_in_a_fresh_process(module, name):
    """An interface running antspyx in the node's own process must declare
    ``fresh_process``: in a reused worker, ITK keeps the thread count of the
    first ITK node that worker ran. (AntsMotionCorrection is not listed: it
    already runs antspyx in a child interpreter of its own.)"""
    import importlib

    interface = getattr(importlib.import_module(module), name)
    assert interface.fresh_process is True
