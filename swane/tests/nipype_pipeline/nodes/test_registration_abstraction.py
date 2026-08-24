"""Tests for the backend-aware registration abstraction in ``nodes/utils.py``.

Covers the tool-neutral CPU helpers (C1), the ``engine``-aware
``get_registration_node`` / ``RegistrationNodeWrapper`` (C2) and the
``engine``-aware ``apply_registration_node`` with ANTs ``which_to_invert``
wiring (C3). Only construction state is inspected; nothing is executed.
"""

import pytest

from nipype import Node
from nipype.interfaces.fsl import BET

from swane.config.config_enums import CoreLimit, RegistrationEngine
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow


def _iface(node):
    """Interface class name of a node."""
    return type(node.interface).__name__


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


# --------------------------------------------------------------------------- #
# C2: engine-aware get_registration_node + RegistrationNodeWrapper
# --------------------------------------------------------------------------- #
class TestGetRegistrationNode:
    def _call(self, engine, make_nifti, **kwargs):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        wf = CustomWorkflow(name="wf")
        # Feed moving/reference as (node, field) connections, exactly as the
        # abstracted workflows do -- the string paths are a different, rarely
        # exercised code path.
        src = Node(IdentityInterface(fields=["moving", "reference"]), name="src")
        return get_registration_node(
            name="reg",
            engine=engine,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            **kwargs,
        )

    def test_fsl_linear_wrapper(self, make_nifti):
        wrap = self._call(RegistrationEngine.FSL, make_nifti, is_volumetric=True)
        assert _iface(wrap.out_registered_node) == "FLIRT"
        assert wrap.engine == RegistrationEngine.FSL
        assert wrap.fwd_transforms == [(wrap.out_registered_node, "out_matrix_file")]
        # FSL/Synth carry no which-to-invert flags.
        assert wrap.fwd_which_to_invert is None
        assert wrap.inv_which_to_invert is None

    def test_fsl_nonlinear_wrapper(self, make_nifti):
        wrap = self._call(
            RegistrationEngine.FSL, make_nifti, non_linear=True, inverse=True
        )
        assert _iface(wrap.out_registered_node) == "FNIRT"
        assert wrap.fwd_transforms == [(wrap.out_registered_node, "fieldcoeff_file")]
        assert wrap.inv_transforms == [(wrap.inv_warp_node, "inverse_warp")]

    def test_synth_wrapper(self, make_nifti):
        wrap = self._call(RegistrationEngine.SYNTH, make_nifti)
        assert _iface(wrap.out_registered_node) == "SynthMorphReg"
        assert wrap.engine == RegistrationEngine.SYNTH
        assert wrap.fwd_transforms == [(wrap.out_registered_node, "warp_file")]
        assert wrap.fwd_which_to_invert is None

    def test_ants_linear_wrapper(self, make_nifti):
        wrap = self._call(RegistrationEngine.ANTS, make_nifti, is_volumetric=True)
        node = wrap.out_registered_node
        assert _iface(node) == "AntsRegistration"
        assert wrap.engine == RegistrationEngine.ANTS
        # Linear volumetric mirrors FSL dof=6 -> a rigid ANTs transform.
        assert node.inputs.transform_type == "Rigid"
        assert wrap.fwd_transforms == [(node, "fwd_transforms")]
        assert wrap.inv_transforms == [(node, "inv_transforms")]
        # The which-to-invert flags are wired straight from the node.
        assert wrap.fwd_which_to_invert == (node, "fwd_which_to_invert")
        assert wrap.inv_which_to_invert == (node, "inv_which_to_invert")

    def test_ants_nonvolumetric_linear_is_affine(self, make_nifti):
        wrap = self._call(RegistrationEngine.ANTS, make_nifti, is_volumetric=False)
        # 2D / non-volumetric mirrors FLIRT's default dof=12 -> affine.
        assert wrap.out_registered_node.inputs.transform_type == "Affine"

    def test_ants_nonlinear_wrapper(self, make_nifti):
        wrap = self._call(RegistrationEngine.ANTS, make_nifti, non_linear=True)
        node = wrap.out_registered_node
        assert _iface(node) == "AntsRegistration"
        assert node.inputs.transform_type == "SyN"
        assert wrap.fwd_transforms == [(node, "fwd_transforms")]


class TestResolveRegistrationEngine:
    def test_default_is_ants(self, global_config):
        from swane.config.config_enums import GlobalPrefCategoryList
        from swane.nipype_pipeline.nodes.utils import resolve_registration_engine

        synth = global_config[GlobalPrefCategoryList.SYNTH]
        assert resolve_registration_engine(synth) == RegistrationEngine.ANTS

    def test_ants_downgraded_to_fsl_when_disallowed(self, global_config):
        from swane.config.config_enums import GlobalPrefCategoryList
        from swane.nipype_pipeline.nodes.utils import resolve_registration_engine

        synth = global_config[GlobalPrefCategoryList.SYNTH]
        assert (
            resolve_registration_engine(synth, allow_ants=False)
            == RegistrationEngine.FSL
        )

    def test_synth_honoured_even_when_ants_disallowed(self, global_config):
        from swane.config.config_enums import GlobalPrefCategoryList
        from swane.nipype_pipeline.nodes.utils import resolve_registration_engine

        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["engine"] = "SYNTH"
        assert (
            resolve_registration_engine(synth, allow_ants=False)
            == RegistrationEngine.SYNTH
        )
