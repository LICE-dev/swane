"""Regression: NO_LIMIT must never reserve more nipype procs than allocated.

``get_tool_cpu_config`` answers ``cpu_count()`` for ``CoreLimit.NO_LIMIT`` with
``hard=False``, meaning "use every core, keep nipype unaware". A tool with no
soft env-var knob (antspynet deskull, AntsRegistration, SynthSeg) cannot honour
the second half: it falls through to the nipype-aware branch and reserves that
count as ``n_procs``. On any host where ``cpu_count()`` exceeds the cores the
subject allocated, ``MultiProc._prerun_check`` then refuses the *whole*
workflow with "Insufficient resources available for job" before a single node
runs.
"""

from multiprocessing import cpu_count

import pytest

from nipype import Node

from swane.config.config_enums import CoreLimit, DeskullEngine, DeskullModality
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from swane.nipype_pipeline.nodes.utils import (
    apply_tool_num_threads,
    get_deskull_node,
)

# The bug only shows where the host has more cores than the subject allocated.
_ALLOCATED = 2
pytestmark = pytest.mark.skipif(
    cpu_count() <= _ALLOCATED,
    reason="needs a host with more cores than the allocated budget",
)


def test_antspynet_deskull_no_limit_stays_within_the_budget():
    node = get_deskull_node(
        name="d",
        deskull_engine=DeskullEngine.ANTSPYNET,
        deskull_modality=DeskullModality.NODIF,
        mask=True,
        max_cpu=_ALLOCATED,
        multicore_node_limit=CoreLimit.NO_LIMIT,
    )
    assert node.n_procs <= _ALLOCATED
    assert node.inputs.num_threads <= _ALLOCATED


def test_apply_tool_num_threads_caps_the_nipype_aware_branch():
    node = Node(AntsPyNetBrainExtraction(), name="n")
    apply_tool_num_threads(node, cpu_count(), hard=False, max_cpu=_ALLOCATED)
    assert node.n_procs == _ALLOCATED
    assert node.inputs.num_threads == _ALLOCATED


def test_soft_env_var_path_is_untouched_by_the_cap():
    """SynthStrip really can hide its threads from nipype: it must keep doing so."""
    node = Node(SynthStrip(), name="n")
    apply_tool_num_threads(
        node,
        cpu_count(),
        hard=False,
        soft_env_vars=("OMP_NUM_THREADS",),
        max_cpu=_ALLOCATED,
    )
    assert node.n_procs == 1
    assert node.inputs.environ["OMP_NUM_THREADS"] == str(cpu_count())
