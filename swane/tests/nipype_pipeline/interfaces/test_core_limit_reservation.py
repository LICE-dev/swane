"""Tests for the hard-cap reservation policy.

All multicore tools must perform a hard-cap reservation where `n_procs` and
`num_threads` are both set to `min(threads, max_cpu)`, making Nipype fully
aware of the resource usage.
"""

from multiprocessing import cpu_count
import pytest
from nipype import Node

from swane.config.config_enums import DeskullEngine, DeskullModality
from swane.nipype_pipeline.interfaces.ants.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
from swane.nipype_pipeline.interfaces.freesurfer.SynthStrip import SynthStrip
from swane.nipype_pipeline.interfaces.utils import (
    apply_tool_num_threads,
    get_deskull_node,
    get_tool_cpu_config,
    get_synth_cpu_config,
)

_ALLOCATED = 2
pytestmark = pytest.mark.skipif(
    cpu_count() <= _ALLOCATED,
    reason="needs a host with more cores than the allocated budget",
)


def test_get_tool_cpu_config_uses_max_cpu():
    # When limit_synth_cores is False, it returns max_cpu (or cpu_count() if max_cpu<=0).
    assert (
        get_tool_cpu_config(max_cpu=_ALLOCATED, limit_synth_cores=False) == _ALLOCATED
    )
    assert get_tool_cpu_config(max_cpu=0, limit_synth_cores=False) == cpu_count()


def test_get_synth_cpu_config_respects_limit_cores_flag():
    # Synth strip falls under get_tool_cpu_config/get_synth_cpu_config which cap to SYNTH_CORE_LIMIT if true.
    # Note: SYNTH_CORE_LIMIT is typically 4. Since _ALLOCATED = 2, min(4, 2) = 2.
    assert (
        get_synth_cpu_config(max_cpu=_ALLOCATED, limit_synth_cores=True) == _ALLOCATED
    )
    assert (
        get_synth_cpu_config(max_cpu=_ALLOCATED, limit_synth_cores=False) == _ALLOCATED
    )


def test_antspynet_deskull_stays_within_the_budget():
    node = get_deskull_node(
        name="d",
        deskull_engine=DeskullEngine.ANTSPYNET,
        deskull_modality=DeskullModality.NODIF,
        mask=True,
        max_cpu=_ALLOCATED,
        limit_synth_cores=False,
    )
    assert node.n_procs <= _ALLOCATED
    assert node.inputs.num_threads <= _ALLOCATED


def test_synthstrip_deskull_stays_within_the_budget():
    node = get_deskull_node(
        name="d",
        deskull_engine=DeskullEngine.SYNTHSTRIP,
        deskull_modality=DeskullModality.T1,
        max_cpu=_ALLOCATED,
        limit_synth_cores=True,
    )
    assert node.n_procs <= _ALLOCATED
    assert node.inputs.num_threads <= _ALLOCATED


def test_apply_tool_num_threads_caps_both_n_procs_and_num_threads():
    node = Node(AntsPyNetBrainExtraction(), name="n")
    # Even if threads > max_cpu, it is capped.
    apply_tool_num_threads(node, threads=cpu_count(), max_cpu=_ALLOCATED)
    assert node.n_procs == _ALLOCATED
    assert node.inputs.num_threads == _ALLOCATED

    # If threads < max_cpu, it uses threads.
    apply_tool_num_threads(node, threads=1, max_cpu=_ALLOCATED)
    assert node.n_procs == 1
    assert node.inputs.num_threads == 1
