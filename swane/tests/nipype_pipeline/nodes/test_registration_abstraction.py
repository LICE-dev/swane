"""Tests for the backend-aware registration abstraction in ``nodes/utils.py``.

Covers the tool-neutral CPU helpers (C1), the ``engine``-aware
``get_registration_node`` / ``RegistrationNodeWrapper`` (C2) and the
``engine``-aware ``apply_registration_node`` with ANTs ``which_to_invert``
wiring (C3). Only construction state is inspected; nothing is executed.
"""

import pytest

from nipype import Node
from nipype.interfaces.fsl import BET

from swane.config.config_enums import CoreLimit


# --------------------------------------------------------------------------- #
# C1: tool-neutral CPU helpers
# --------------------------------------------------------------------------- #
class TestToolCpuHelpers:
    def test_get_tool_cpu_config_soft_cap(self):
        from swane.nipype_pipeline.nodes.utils import get_tool_cpu_config

        threads, hard = get_tool_cpu_config(
            max_cpu=4,
            multicore_node_limit=CoreLimit.SOFT_CAP,
            limit_synth_cores=False,
        )
        assert (threads, hard) == (4, False)

    def test_get_tool_cpu_config_hard_cap(self):
        from swane.nipype_pipeline.nodes.utils import get_tool_cpu_config

        threads, hard = get_tool_cpu_config(
            max_cpu=4,
            multicore_node_limit=CoreLimit.HARD_CAP,
            limit_synth_cores=False,
        )
        assert (threads, hard) == (4, True)

    def test_old_helper_names_are_aliases(self):
        from swane.nipype_pipeline.nodes import utils

        assert utils.get_synth_cpu_config is utils.get_tool_cpu_config
        assert utils.apply_synth_num_threads is utils.apply_tool_num_threads

    def test_apply_tool_num_threads_hard_sets_nprocs(self):
        from swane.nipype_pipeline.nodes.utils import apply_tool_num_threads
        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration

        node = Node(AntsRegistration(), name="antsreg")
        apply_tool_num_threads(node, threads=3, hard=True)
        assert node.inputs.num_threads == 3
        assert node.n_procs == 3

    def test_apply_tool_num_threads_soft_env_vars(self):
        from swane.nipype_pipeline.nodes.utils import apply_tool_num_threads

        node = Node(BET(), name="bet")
        apply_tool_num_threads(
            node, threads=2, hard=False, soft_env_vars=("OMP_NUM_THREADS",)
        )
        assert node.inputs.environ["OMP_NUM_THREADS"] == "2"
        # Soft cap keeps nipype unaware of the reservation.
        assert node.n_procs in (None, 1)

    def test_apply_tool_num_threads_no_env_vars_is_always_aware(self):
        """A tool with no soft env vars (SynthSeg, ANTs) can never hide its
        threads from nipype -- ``num_threads`` is set and ``n_procs`` follows it
        even in the soft-cap case."""
        from swane.nipype_pipeline.nodes.utils import apply_tool_num_threads
        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration

        node = Node(AntsRegistration(), name="antsreg")
        apply_tool_num_threads(node, threads=2, hard=False)
        assert node.inputs.num_threads == 2
        assert node.n_procs == 2
