"""Tests for the backend-aware registration abstraction in ``nodes/utils.py``.

Covers the tool-neutral CPU helpers (C1), the ``engine``-aware
``get_registration_node`` / ``RegistrationNodeWrapper`` (C2) and the
``engine``-aware ``apply_registration_node`` with ANTs ``which_to_invert``
wiring (C3). All but the trailing ``heavy`` class inspect construction state
only; nothing is executed. The ``heavy`` class runs a real antspyx
registration to guard the composed-field boundary round-trip end-to-end.
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

    def test_fsl_nonlinear_string_path_wires_invwarp_reference(self, make_nifti):
        """The rarely-used string-path branch must set InvWarp's real mandatory
        ``reference`` trait; ``ref_file`` does not exist and raises at build."""
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        wf = CustomWorkflow(name="wf")
        moving = make_nifti("m.nii.gz", shape=(6, 6, 6))
        reference = make_nifti("r.nii.gz", shape=(6, 6, 6))
        wrap = get_registration_node(
            name="reg",
            engine=RegistrationEngine.FSL,
            workflow=wf,
            moving=moving,
            reference=reference,
            non_linear=True,
            inverse=True,
        )
        assert wrap.inv_warp_node.inputs.reference == moving

    def test_ants_test_run_is_off_by_default(self, make_nifti):
        """Full accuracy unless the sweep explicitly asks for the fast path."""
        from nipype.interfaces.base import isdefined

        wrap = self._call(RegistrationEngine.ANTS, make_nifti, is_volumetric=True)
        assert not isdefined(wrap.out_registered_node.inputs.test_run)

    def test_ants_test_run_propagates_to_the_node(self, make_nifti):
        """test_run reaches AntsRegistration just as it reaches FNIRT/SynthMorph."""
        wrap = self._call(
            RegistrationEngine.ANTS, make_nifti, is_volumetric=True, test_run=True
        )
        assert wrap.out_registered_node.inputs.test_run is True


class TestGetRegistrationNodeMovingMask:
    """The registration accepts an optional ``moving_mask`` (a metric mask/weight
    in moving space, used by seeg_ct's electrode weighting). On ANTs it becomes
    ``AntsRegistration.moving_mask``; on the FSL linear branch the same map is
    wired as ``FLIRT.in_weight``. Synth ignores it. When absent the ANTs input
    stays undefined."""

    def _ants(self, moving_mask):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        wf = CustomWorkflow(name="wf")
        src = Node(
            IdentityInterface(fields=["moving", "reference", "weight"]), name="src"
        )
        wrap = get_registration_node(
            name="reg",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            is_volumetric=True,
            moving_mask=moving_mask,
        )
        return wf, src, wrap

    def test_moving_mask_connection(self, make_nifti):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        wf = CustomWorkflow(name="wf")
        src = Node(
            IdentityInterface(fields=["moving", "reference", "weight"]), name="src"
        )
        wrap = get_registration_node(
            name="reg",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            is_volumetric=True,
            moving_mask=[src, "weight"],
        )
        node = wrap.out_registered_node
        assert (src, "weight", "moving_mask") in _incoming(wf, node)

    def test_moving_mask_string_set_directly(self, make_nifti):
        mask = make_nifti("mask.nii.gz", shape=(6, 6, 6))
        _, _, wrap = self._ants(mask)
        assert wrap.out_registered_node.inputs.moving_mask == mask

    def test_moving_mask_undefined_when_absent(self, make_nifti):
        from nipype.interfaces.base import isdefined

        _, _, wrap = self._ants(None)
        assert not isdefined(wrap.out_registered_node.inputs.moving_mask)

    def test_fsl_linear_wires_moving_mask_as_in_weight(self, make_nifti):
        """On the FSL linear branch the moving_mask is wired as FLIRT.in_weight
        (its per-voxel registration weight analogue)."""
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        wf = CustomWorkflow(name="wf")
        src = Node(
            IdentityInterface(fields=["moving", "reference", "weight"]), name="src"
        )
        wrap = get_registration_node(
            name="reg",
            engine=RegistrationEngine.FSL,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            is_volumetric=True,
            moving_mask=[src, "weight"],
        )
        assert _iface(wrap.out_registered_node) == "FLIRT"
        assert (src, "weight", "in_weight") in _incoming(wf, wrap.out_registered_node)

    def test_fsl_moving_mask_string_set_directly(self, make_nifti):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        mask = make_nifti("mask.nii.gz", shape=(6, 6, 6))
        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["moving", "reference"]), name="src")
        wrap = get_registration_node(
            name="reg",
            engine=RegistrationEngine.FSL,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            is_volumetric=True,
            moving_mask=mask,
        )
        assert wrap.out_registered_node.inputs.in_weight == mask


class TestGetRegistrationNodeRegisteredAndMapMoving:
    """The wrapper exposes the moving image resampled into reference space
    (``registered_node``/``registered_field``) for every backend, and
    ``map_moving`` builds the registration as a MapNode iterating the moving
    image (used by venous_ct's contrast series)."""

    def _wrap(self, engine, non_linear=False, is_volumetric=True, map_moving=False):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import get_registration_node

        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["moving", "reference"]), name="src")
        wrap = get_registration_node(
            name="reg",
            engine=engine,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            non_linear=non_linear,
            is_volumetric=is_volumetric,
            map_moving=map_moving,
        )
        return wf, src, wrap

    def test_registered_field_fsl_linear(self, make_nifti):
        _, _, wrap = self._wrap(RegistrationEngine.FSL)
        assert wrap.registered_field == "out_file"
        assert _iface(wrap.registered_node) == "FLIRT"

    def test_registered_field_fsl_nonlinear(self, make_nifti):
        _, _, wrap = self._wrap(RegistrationEngine.FSL, non_linear=True)
        assert wrap.registered_field == "warped_file"
        assert _iface(wrap.registered_node) == "FNIRT"

    def test_registered_field_ants(self, make_nifti):
        _, _, wrap = self._wrap(RegistrationEngine.ANTS)
        assert wrap.registered_field == "warped_file"
        assert _iface(wrap.registered_node) == "AntsRegistration"

    def test_registered_field_synth(self, make_nifti):
        _, _, wrap = self._wrap(RegistrationEngine.SYNTH)
        assert wrap.registered_field == "out_file"
        assert _iface(wrap.registered_node) == "SynthMorphReg"

    def test_map_moving_default_builds_plain_node(self, make_nifti):
        from nipype import MapNode

        _, _, wrap = self._wrap(RegistrationEngine.ANTS)
        assert not isinstance(wrap.registered_node, MapNode)

    def test_map_moving_ants_iterates_moving(self, make_nifti):
        from nipype import MapNode

        _, _, wrap = self._wrap(RegistrationEngine.ANTS, map_moving=True)
        assert isinstance(wrap.registered_node, MapNode)
        assert wrap.registered_node.iterfield == ["moving"]

    def test_map_moving_fsl_linear_iterates_in_file(self, make_nifti):
        from nipype import MapNode

        _, _, wrap = self._wrap(RegistrationEngine.FSL, map_moving=True)
        assert isinstance(wrap.registered_node, MapNode)
        assert wrap.registered_node.iterfield == ["in_file"]

    def test_map_moving_fsl_nonlinear_raises(self, make_nifti):
        with pytest.raises(ValueError):
            self._wrap(RegistrationEngine.FSL, non_linear=True, map_moving=True)


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


def _incoming(workflow, dst_node):
    """List of (src_node, src_field, dst_field) edges feeding ``dst_node``."""
    conns = []
    for src, dst, data in workflow._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


# --------------------------------------------------------------------------- #
# C3: engine-aware apply_registration_node + which_to_invert wiring
# --------------------------------------------------------------------------- #
class TestApplyRegistrationNode:
    def _reg_and_apply(self, make_nifti, *, non_linear, inverse, labelmap=False):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            get_registration_node,
            apply_registration_node,
        )

        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["moving", "reference"]), name="src")
        reg = get_registration_node(
            name="reg",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "moving"],
            reference=[src, "reference"],
            non_linear=non_linear,
            inverse=inverse,
        )
        apply_node = apply_registration_node(
            name="apply",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            warp=None,
            moving=[src, "moving"],
            reference=[src, "reference"],
            registration=reg,
            inverse=inverse,
            non_linear=non_linear,
            labelmap=labelmap,
        )
        return wf, reg, apply_node

    def test_ants_apply_interpolator_linear(self, make_nifti):
        _, _, apply_node = self._reg_and_apply(
            make_nifti, non_linear=False, inverse=False, labelmap=False
        )
        assert _iface(apply_node) == "AntsApplyTransforms"
        assert apply_node.inputs.interpolator == "linear"

    def test_ants_apply_interpolator_labelmap(self, make_nifti):
        _, _, apply_node = self._reg_and_apply(
            make_nifti, non_linear=False, inverse=False, labelmap=True
        )
        # antspyx spelling, NOT FSL's nearestneighbour.
        assert apply_node.inputs.interpolator == "nearestNeighbor"

    def test_ants_forward_wires_transformlist_and_flags(self, make_nifti):
        wf, reg, apply_node = self._reg_and_apply(
            make_nifti, non_linear=True, inverse=False
        )
        ants = reg.out_registered_node
        incoming = _incoming(wf, apply_node)
        assert (ants, "fwd_transforms", "transformlist") in incoming
        # The which_to_invert flags MUST be wired -- never left to the antspyx
        # default (see the silent-bug guard).
        assert (ants, "fwd_which_to_invert", "which_to_invert") in incoming

    def test_ants_inverse_linear_wires_inv_which_to_invert(self, make_nifti):
        """Regression guard: a linear inverse apply must carry which_to_invert
        from the node's inv_which_to_invert (which is [True] for a lone affine),
        not the antspyx default that would apply the matrix un-inverted."""
        wf, reg, apply_node = self._reg_and_apply(
            make_nifti, non_linear=False, inverse=True
        )
        ants = reg.out_registered_node
        incoming = _incoming(wf, apply_node)
        assert (ants, "inv_transforms", "transformlist") in incoming
        assert (ants, "inv_which_to_invert", "which_to_invert") in incoming

    def test_ants_linear_inverse_flags_value_is_true(self, tmp_path):
        """The wired source really yields [True] for a lone affine: exercise
        AntsRegistration._list_outputs with a single .mat inverse transform."""
        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration

        node = AntsRegistration()
        affine = str(tmp_path / "reg_0GenericAffine.mat")
        open(affine, "w").close()
        node._fwd = [affine]
        node._inv = [affine]
        node._warped = str(tmp_path / "warped.nii.gz")
        outputs = node._list_outputs()
        assert outputs["inv_which_to_invert"] == [True]
        assert outputs["fwd_which_to_invert"] == [False]

    def test_fsl_apply_unchanged(self, make_nifti):
        from swane.nipype_pipeline.nodes.utils import apply_registration_node

        wf = CustomWorkflow(name="wf")
        from nipype.interfaces.utility import IdentityInterface

        src = Node(IdentityInterface(fields=["warp", "reference"]), name="src")
        apply_node = apply_registration_node(
            name="apply",
            engine=RegistrationEngine.FSL,
            workflow=wf,
            warp=[src, "warp"],
            moving=make_nifti("m.nii.gz", shape=(6, 6, 6)),
            reference=[src, "reference"],
            non_linear=False,
            labelmap=True,
        )
        assert _iface(apply_node) == "ApplyXFM"
        assert apply_node.inputs.interp == "nearestneighbour"

    def test_synth_apply_unchanged(self, make_nifti):
        from swane.nipype_pipeline.nodes.utils import apply_registration_node

        wf = CustomWorkflow(name="wf")
        from nipype.interfaces.utility import IdentityInterface

        src = Node(IdentityInterface(fields=["warp"]), name="src")
        apply_node = apply_registration_node(
            name="apply",
            engine=RegistrationEngine.SYNTH,
            workflow=wf,
            warp=[src, "warp"],
            moving=make_nifti("m.nii.gz", shape=(6, 6, 6)),
            reference=make_nifti("r.nii.gz", shape=(6, 6, 6)),
            labelmap=True,
        )
        assert _iface(apply_node) == "SynthMorphApply"
        assert apply_node.inputs.method == "nearest"


# --------------------------------------------------------------------------- #
# C3 (Phase 2): single composed field crossing a workflow boundary
#
# A nonlinear-warp consumer (flat1, func_map AI, tractography) receives one
# composed displacement field per direction from the MainWorkflow boundary and
# calls ``apply_registration_node(warp=[inputnode, "<field>"], registration=None)``.
# The ANTs branch must resample through that single field with no wrapper and no
# ``which_to_invert`` (the composition already baked the direction in).
# --------------------------------------------------------------------------- #
class TestApplyRegistrationNodeSingleField:
    def _apply_single_field(self, *, labelmap=False, non_linear=True):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import apply_registration_node

        wf = CustomWorkflow(name="wf")
        src = Node(
            IdentityInterface(fields=["ref_2_sym_warp", "moving", "reference"]),
            name="src",
        )
        node = apply_registration_node(
            name="ai_2_sym",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            warp=[src, "ref_2_sym_warp"],
            moving=[src, "moving"],
            reference=[src, "reference"],
            non_linear=non_linear,
            registration=None,
            labelmap=labelmap,
        )
        return wf, src, node

    def test_builds_ants_apply(self):
        _, _, node = self._apply_single_field()
        assert _iface(node) == "AntsApplyTransforms"

    def test_transformlist_fed_via_merge_from_boundary(self):
        """The single boundary File is lifted to the one-element list that
        ``AntsApplyTransforms.transformlist`` (a List trait) requires, via a
        ``Merge(1)`` node whose ``in1`` comes straight from the boundary field."""
        wf, src, node = self._apply_single_field()
        incoming = _incoming(wf, node)
        tl = [c for c in incoming if c[2] == "transformlist"]
        assert len(tl) == 1
        merge_node, src_field, _ = tl[0]
        assert _iface(merge_node) == "Merge"
        assert src_field == "out"
        # the merge's in1 comes from the boundary (src, "ref_2_sym_warp")
        assert (src, "ref_2_sym_warp", "in1") in _incoming(wf, merge_node)

    def test_which_to_invert_is_never_wired_or_set(self):
        """The composed field is already directional: no invert flags cross the
        boundary and none are set on the apply node."""
        from nipype.interfaces.base import isdefined

        wf, _, node = self._apply_single_field()
        assert not any(c[2] == "which_to_invert" for c in _incoming(wf, node))
        assert not isdefined(node.inputs.which_to_invert)

    def test_labelmap_sets_nearest_neighbor(self):
        _, _, node = self._apply_single_field(labelmap=True)
        assert node.inputs.interpolator == "nearestNeighbor"

    def test_linear_boundary_field_also_supported(self):
        """A composed *linear* boundary field takes the same single-field path
        (venous_ct / seeg_ct resample through one composed affine field)."""
        _, _, node = self._apply_single_field(non_linear=False)
        assert _iface(node) == "AntsApplyTransforms"


# --------------------------------------------------------------------------- #
# C5: round-trip correctness guard (risk #1 -- direction/space of composition)
#
# Session A already proves, at the node level, that resampling through the
# single composed field matches resampling through the raw ordered list. This
# guard closes the loop through the *abstraction*: it composes the boundary
# field with AntsComposeTransform, then applies it via
# ``apply_registration_node(registration=None)`` -- the exact single-field path
# (Merge(1) -> transformlist, no which_to_invert) the Phase-2 consumers use --
# and asserts the result is identical to the raw-list apply, both directions.
#
# If this fails, the composition's direction/space or which_to_invert handling
# is wrong: the fix belongs in AntsComposeTransform (Session A), not here.
# --------------------------------------------------------------------------- #
@pytest.mark.heavy
class TestAbstractionSingleFieldRoundTrip:
    @staticmethod
    def _sphere(shape, center, radius):
        import numpy as np

        grid = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]].astype(float)
        distance = sum((grid[i] - center[i]) ** 2 for i in range(3))
        return (distance < radius**2).astype(np.float32)

    @staticmethod
    def _raw_apply(input_image, reference, transformlist, which_to_invert, out_file):
        """Resample the raw ordered transform list directly (the reference)."""
        import nibabel as nib
        from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms

        node = AntsApplyTransforms()
        node.inputs.input_image = input_image
        node.inputs.reference_image = reference
        node.inputs.transformlist = transformlist
        if which_to_invert is not None:
            node.inputs.which_to_invert = which_to_invert
        node.inputs.out_file = out_file
        node.run()
        return nib.load(node._list_outputs()["out_file"]).get_fdata()

    @staticmethod
    def _compose(transformlist, which_to_invert, reference, workspace, directory):
        """Flatten the ordered list into one boundary field (as the producer does)."""
        import os
        from swane.nipype_pipeline.nodes.AntsComposeTransform import (
            AntsComposeTransform,
        )

        os.mkdir(str(workspace / directory))
        os.chdir(str(workspace / directory))
        node = AntsComposeTransform()
        node.inputs.transformlist = transformlist
        node.inputs.which_to_invert = which_to_invert
        node.inputs.reference_image = reference
        node.run()
        field = node._list_outputs()["out_field"]
        os.chdir(str(workspace))
        return field

    @staticmethod
    def _apply_through_abstraction(field, moving, reference, workspace, name):
        """Apply the single boundary field via the real abstraction workflow."""
        import glob
        import os
        import nibabel as nib
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import apply_registration_node

        run_dir = str(workspace / (name + "_run"))
        wf = CustomWorkflow(name=name)
        wf.base_dir = run_dir
        src = Node(
            IdentityInterface(fields=["field", "moving", "reference"]), name="boundary"
        )
        src.inputs.field = field
        src.inputs.moving = moving
        src.inputs.reference = reference
        apply_registration_node(
            name="apply",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            warp=[src, "field"],
            moving=[src, "moving"],
            reference=[src, "reference"],
            non_linear=True,
            registration=None,
            out_file="through_abstraction.nii.gz",
        )
        wf.run()
        os.chdir(str(workspace))
        matches = glob.glob(
            os.path.join(run_dir, "**", "through_abstraction.nii.gz"), recursive=True
        )
        assert matches, "the abstraction apply produced no output file"
        return nib.load(matches[0]).get_fdata()

    def test_single_field_apply_matches_raw_list(self, workspace, make_nifti):
        """Both directions: the abstraction's single-field apply of the composed
        boundary field reproduces the raw ordered-list apply within tolerance."""
        import numpy as np
        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration

        fixed = make_nifti(
            "fixed.nii.gz", data=self._sphere((32, 32, 32), (16, 16, 16), 8)
        )
        moving = make_nifti(
            "moving.nii.gz",
            data=self._sphere((32, 32, 32), (18, 15, 16), 7),
            affine=np.diag([1.2, 1.2, 1.2, 1.0]),
        )

        reg = AntsRegistration()
        reg.inputs.fixed = fixed
        reg.inputs.moving = moving
        reg.inputs.transform_type = "SyN"
        reg.inputs.test_run = True
        reg.run()
        reg_out = reg._list_outputs()

        # forward: moving -> fixed, composed on the fixed grid
        raw_forward = self._raw_apply(
            moving,
            fixed,
            reg_out["fwd_transforms"],
            reg_out["fwd_which_to_invert"],
            "raw_forward.nii.gz",
        )
        fwd_field = self._compose(
            reg_out["fwd_transforms"],
            reg_out["fwd_which_to_invert"],
            fixed,
            workspace,
            "compose_fwd",
        )
        abstraction_forward = self._apply_through_abstraction(
            fwd_field, moving, fixed, workspace, "fwd"
        )
        assert np.count_nonzero(raw_forward) > 100
        assert np.allclose(raw_forward, abstraction_forward, atol=1e-4)

        # inverse: fixed -> moving, composed on the moving grid. The inverse list
        # carries the forward affine, so its invert flag must be baked into the
        # field for this to hold through the flag-less single-field path.
        raw_inverse = self._raw_apply(
            fixed,
            moving,
            reg_out["inv_transforms"],
            reg_out["inv_which_to_invert"],
            "raw_inverse.nii.gz",
        )
        inv_field = self._compose(
            reg_out["inv_transforms"],
            reg_out["inv_which_to_invert"],
            moving,
            workspace,
            "compose_inv",
        )
        abstraction_inverse = self._apply_through_abstraction(
            inv_field, fixed, moving, workspace, "inv"
        )
        assert np.count_nonzero(raw_inverse) > 100
        assert np.allclose(raw_inverse, abstraction_inverse, atol=1e-4)


# --------------------------------------------------------------------------- #
# C3 (Phase 3): ANTS-only multi-warp apply path (``registration_stack``)
#
# The resting-state func -> ref -> mni concatenation stacks two registration
# wrappers into ONE ``AntsApplyTransforms``: one ravel ``Merge`` builds the
# ordered ``transformlist``, a parallel ravel ``Merge`` builds the matching
# ``which_to_invert``. The stack order IS the transformlist order
# (output -> input; ANTs applies the list right-to-left), so the caller passes
# ``[ref_2_mni, func_2_ref]`` to resample a func image into MNI space.
# --------------------------------------------------------------------------- #
class TestApplyRegistrationNodeStack:
    def _stack(self, *, inverse=False, engine=RegistrationEngine.ANTS, **kwargs):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            apply_registration_node,
            get_registration_node,
        )

        wf = CustomWorkflow(name="wf")
        src = Node(
            IdentityInterface(fields=["func", "ref", "mni"]),
            name="src",
        )
        # ref -> mni (nonlinear) and func -> ref (linear), the resting concat
        reg_mni = get_registration_node(
            name="ref_2_mni",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "ref"],
            reference=[src, "mni"],
            non_linear=True,
        )
        reg_ref = get_registration_node(
            name="func_2_ref",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "func"],
            reference=[src, "ref"],
            non_linear=False,
        )
        apply_node = apply_registration_node(
            name="func2mni",
            engine=engine,
            workflow=wf,
            warp=None,
            moving=[src, "func"],
            reference=[src, "mni"],
            non_linear=True,
            registration_stack=[reg_mni, reg_ref],
            inverse=inverse,
            **kwargs,
        )
        return wf, reg_mni, reg_ref, apply_node

    def _merge_feeding(self, wf, apply_node, dst_field):
        """The Merge node feeding ``dst_field`` of the apply node."""
        edges = [c for c in _incoming(wf, apply_node) if c[2] == dst_field]
        assert len(edges) == 1
        merge_node, src_field, _ = edges[0]
        assert _iface(merge_node) == "Merge"
        assert src_field == "out"
        return merge_node

    def test_registration_stack_builds_ants_apply_node(self):
        _, _, _, apply_node = self._stack()
        assert _iface(apply_node) == "AntsApplyTransforms"

    def test_registration_stack_transformlist_merge_is_ravel_and_sized_to_the_stack(
        self,
    ):
        wf, _, _, apply_node = self._stack()
        merge = self._merge_feeding(wf, apply_node, "transformlist")
        assert merge.interface._numinputs == 2
        assert merge.inputs.ravel_inputs is True

    def test_registration_stack_which_to_invert_merge_is_ravel_and_sized_to_the_stack(
        self,
    ):
        wf, _, _, apply_node = self._stack()
        merge = self._merge_feeding(wf, apply_node, "which_to_invert")
        assert merge.interface._numinputs == 2
        assert merge.inputs.ravel_inputs is True

    def test_registration_stack_transformlist_order_is_output_to_input(self):
        """``in1`` is the ref->mni registration, ``in2`` the func->ref one.

        ANTs applies a transform list right-to-left, so the last entry acts
        first: the func image must meet its func->ref transform first and the
        ref->mni transform second. Reversing this silently resamples wrong.
        """
        wf, reg_mni, reg_ref, apply_node = self._stack()
        merge = self._merge_feeding(wf, apply_node, "transformlist")
        incoming = _incoming(wf, merge)
        assert (reg_mni.out_registered_node, "fwd_transforms", "in1") in incoming
        assert (reg_ref.out_registered_node, "fwd_transforms", "in2") in incoming

    def test_registration_stack_which_to_invert_order_matches_the_transformlist(self):
        """The flag merge must mirror the transform merge slot for slot."""
        wf, reg_mni, reg_ref, apply_node = self._stack()
        merge = self._merge_feeding(wf, apply_node, "which_to_invert")
        incoming = _incoming(wf, merge)
        assert (reg_mni.out_registered_node, "fwd_which_to_invert", "in1") in incoming
        assert (reg_ref.out_registered_node, "fwd_which_to_invert", "in2") in incoming

    def test_registration_stack_inverse_takes_the_inverse_views_slot_for_slot(self):
        """``inverse=True`` swaps each wrapper's forward view for its inverse
        one; it does NOT reorder the stack (the caller owns the order)."""
        wf, reg_mni, reg_ref, apply_node = self._stack(inverse=True)
        tl = _incoming(wf, self._merge_feeding(wf, apply_node, "transformlist"))
        wti = _incoming(wf, self._merge_feeding(wf, apply_node, "which_to_invert"))
        assert (reg_mni.out_registered_node, "inv_transforms", "in1") in tl
        assert (reg_ref.out_registered_node, "inv_transforms", "in2") in tl
        assert (reg_mni.out_registered_node, "inv_which_to_invert", "in1") in wti
        assert (reg_ref.out_registered_node, "inv_which_to_invert", "in2") in wti

    def test_registration_stack_merge_nodes_are_named_after_the_apply_node(self):
        wf, _, _, _ = self._stack()
        names = {node.name for node in wf._graph.nodes()}
        assert "func2mni_transformlist" in names
        assert "func2mni_which_to_invert" in names

    def test_registration_stack_moving_and_reference_still_wired(self):
        wf, _, _, apply_node = self._stack()
        incoming = _incoming(wf, apply_node)
        assert any(c[2] == "input_image" for c in incoming)
        assert any(c[2] == "reference_image" for c in incoming)

    def test_registration_stack_labelmap_and_out_file_still_honoured(self):
        _, _, _, apply_node = self._stack(labelmap=True, out_file="stacked.nii.gz")
        assert apply_node.inputs.interpolator == "nearestNeighbor"
        assert apply_node.inputs.out_file == "stacked.nii.gz"

    # -- misuse guards ----------------------------------------------------- #
    def test_registration_stack_rejects_combining_stack_with_registration(self):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            apply_registration_node,
            get_registration_node,
        )

        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["func", "ref"]), name="src")
        reg = get_registration_node(
            name="func_2_ref",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "func"],
            reference=[src, "ref"],
        )
        with pytest.raises(ValueError, match="mutually exclusive"):
            apply_registration_node(
                name="apply",
                engine=RegistrationEngine.ANTS,
                workflow=wf,
                warp=None,
                moving=[src, "func"],
                reference=[src, "ref"],
                registration=reg,
                registration_stack=[reg],
            )

    def test_registration_stack_rejects_combining_stack_with_bare_warp(self):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            apply_registration_node,
            get_registration_node,
        )

        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["func", "ref", "warp"]), name="src")
        reg = get_registration_node(
            name="func_2_ref",
            engine=RegistrationEngine.ANTS,
            workflow=wf,
            moving=[src, "func"],
            reference=[src, "ref"],
        )
        with pytest.raises(ValueError, match="mutually exclusive"):
            apply_registration_node(
                name="apply",
                engine=RegistrationEngine.ANTS,
                workflow=wf,
                warp=[src, "warp"],
                moving=[src, "func"],
                reference=[src, "ref"],
                registration_stack=[reg],
            )

    def test_registration_stack_rejects_non_ants_engine(self):
        with pytest.raises(ValueError, match="ANTS"):
            self._stack(engine=RegistrationEngine.FSL)

    def test_registration_stack_rejects_empty_stack(self):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import apply_registration_node

        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["func", "ref"]), name="src")
        with pytest.raises(ValueError, match="at least one"):
            apply_registration_node(
                name="apply",
                engine=RegistrationEngine.ANTS,
                workflow=wf,
                warp=None,
                moving=[src, "func"],
                reference=[src, "ref"],
                registration_stack=[],
            )

    def test_registration_stack_rejects_a_non_ants_wrapper_in_the_stack(self):
        """An FSL wrapper carries no ``which_to_invert``: stacking it would
        silently desynchronise the two merges."""
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            apply_registration_node,
            get_registration_node,
        )

        wf = CustomWorkflow(name="wf")
        src = Node(IdentityInterface(fields=["func", "ref"]), name="src")
        fsl_reg = get_registration_node(
            name="func_2_ref",
            engine=RegistrationEngine.FSL,
            workflow=wf,
            moving=[src, "func"],
            reference=[src, "ref"],
        )
        with pytest.raises(ValueError, match="ANTs registration"):
            apply_registration_node(
                name="apply",
                engine=RegistrationEngine.ANTS,
                workflow=wf,
                warp=None,
                moving=[src, "func"],
                reference=[src, "ref"],
                registration_stack=[fsl_reg],
            )


# --------------------------------------------------------------------------- #
# C5 (Phase 3): ordering/direction guard for the multi-warp stack (risk #1)
#
# The resting-state concat resamples a func image straight into MNI space
# through TWO registrations at once. Getting the ``transformlist`` order or the
# ``which_to_invert`` assembly wrong resamples silently into the wrong place --
# no crash, no warning, just wrong science. This runs real antspyx
# registrations on a phantom and checks the production path three ways:
#
#   1. against the hand-built concatenated list (exact: same single
#      interpolation, so the ravel ``Merge`` wiring must reproduce it bit for
#      bit -- this is the abstraction's own contract);
#   2. against a SEQUENTIAL two-step apply (approximate only: stacking does one
#      interpolation where the sequential reference does two, and that blur is
#      physical, not a bug -- hence a geometric agreement bound, not a
#      voxel-wise one);
#   3. against the REVERSED stack as a negative control, which must fail both
#      bounds by a wide margin -- otherwise the guard would not be sensitive to
#      the very mistake it exists to catch.
# --------------------------------------------------------------------------- #
@pytest.mark.heavy
class TestAntsStackRoundTrip:
    @staticmethod
    def _sphere(shape, center, radius):
        import numpy as np

        grid = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]].astype(float)
        distance = sum((grid[i] - center[i]) ** 2 for i in range(3))
        return (distance < radius**2).astype("float32")

    @staticmethod
    def _register(fixed, moving, transform_type, workspace, directory):
        """Run a real antspyx registration in its own directory."""
        import os
        from swane.nipype_pipeline.nodes.AntsRegistration import AntsRegistration

        os.makedirs(str(workspace / directory), exist_ok=True)
        os.chdir(str(workspace / directory))
        node = AntsRegistration()
        node.inputs.fixed = fixed
        node.inputs.moving = moving
        node.inputs.transform_type = transform_type
        node.inputs.test_run = True
        node.run()
        outputs = node._list_outputs()
        os.chdir(str(workspace))
        return outputs

    @staticmethod
    def _direct_apply(
        moving, reference, transformlist, which_to_invert, workspace, name
    ):
        """Resample through a hand-built transform list (the reference path)."""
        import os
        from swane.nipype_pipeline.nodes.AntsApplyTransforms import AntsApplyTransforms

        os.makedirs(str(workspace / ("direct_" + name)), exist_ok=True)
        os.chdir(str(workspace / ("direct_" + name)))
        node = AntsApplyTransforms()
        node.inputs.input_image = moving
        node.inputs.reference_image = reference
        node.inputs.transformlist = list(transformlist)
        node.inputs.which_to_invert = list(which_to_invert)
        node.inputs.out_file = name + ".nii.gz"
        node.run()
        out_file = node._list_outputs()["out_file"]
        os.chdir(str(workspace))
        return out_file

    @staticmethod
    def _stacked_apply(sources, order, moving, reference, workspace, name, inverse):
        """Resample through the real ``registration_stack`` production path.

        ``sources`` maps a key to its ``(transforms, which_to_invert)`` pair;
        ``order`` lists those keys in the intended stack order. Each pair is
        published on one boundary ``IdentityInterface`` and wrapped in a
        :class:`RegistrationNodeWrapper`, so the workflow exercises exactly the
        ravel ``Merge`` -> ``transformlist`` / ``which_to_invert`` wiring that
        ``apply_registration_node`` builds for a real pair of registrations.
        """
        import glob
        import os
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            RegistrationNodeWrapper,
            apply_registration_node,
        )

        run_dir = str(workspace / (name + "_run"))
        workflow = CustomWorkflow(name=name)
        workflow.base_dir = run_dir
        fields = ["moving", "reference"]
        for key in sources:
            fields += [key + "_transforms", key + "_flags"]
        boundary = Node(IdentityInterface(fields=fields), name="boundary")
        boundary.inputs.moving = moving
        boundary.inputs.reference = reference
        for key, (transforms, flags) in sources.items():
            setattr(boundary.inputs, key + "_transforms", list(transforms))
            setattr(boundary.inputs, key + "_flags", list(flags))

        def wrapper(key):
            transform_field = key + "_transforms"
            flag_field = key + "_flags"
            return RegistrationNodeWrapper(
                input_node=boundary,
                out_registered_node=boundary,
                warp=transform_field,
                inv_warp_node=boundary,
                inv_warp=transform_field,
                engine=RegistrationEngine.ANTS,
                fwd_transforms=[(boundary, transform_field)],
                inv_transforms=[(boundary, transform_field)],
                fwd_which_to_invert=(boundary, flag_field),
                inv_which_to_invert=(boundary, flag_field),
            )

        apply_registration_node(
            name="stacked",
            engine=RegistrationEngine.ANTS,
            workflow=workflow,
            warp=None,
            moving=[boundary, "moving"],
            reference=[boundary, "reference"],
            non_linear=True,
            registration_stack=[wrapper(key) for key in order],
            inverse=inverse,
            out_file=name + ".nii.gz",
        )
        workflow.run()
        os.chdir(str(workspace))
        matches = glob.glob(
            os.path.join(run_dir, "**", name + ".nii.gz"), recursive=True
        )
        assert matches, "the stacked apply produced no output file"
        return matches[0]

    @staticmethod
    def _centre_of_mass(data):
        import numpy as np

        indices = np.argwhere(data > 0.5)
        assert len(indices), "the resampled phantom is empty"
        return indices.mean(axis=0)

    def test_stack_roundtrip_matches_concatenated_list_and_sequential(
        self, workspace, make_nifti
    ):
        import numpy as np
        import nibabel as nib

        # three spaces: func -> ref (linear) -> mni (nonlinear), as in the
        # resting-state concatenation.
        shape = (40, 40, 40)
        func = make_nifti("func.nii.gz", data=self._sphere(shape, (20, 20, 20), 7))
        ref = make_nifti("ref.nii.gz", data=self._sphere(shape, (24, 18, 20), 7))
        mni = make_nifti("mni.nii.gz", data=self._sphere(shape, (24, 18, 26), 9))

        func_2_ref = self._register(ref, func, "Rigid", workspace, "reg_func_2_ref")
        ref_2_mni = self._register(mni, ref, "SyN", workspace, "reg_ref_2_mni")
        sources = {
            "mni": (
                ref_2_mni["fwd_transforms"],
                ref_2_mni["fwd_which_to_invert"],
            ),
            "ref": (
                func_2_ref["fwd_transforms"],
                func_2_ref["fwd_which_to_invert"],
            ),
        }

        # --- the production path: stack order = [ref->mni, func->ref] ------- #
        stacked = self._stacked_apply(
            sources, ["mni", "ref"], func, mni, workspace, "stacked", inverse=False
        )

        # 1. exact match against the hand-built concatenated list ------------ #
        handbuilt = self._direct_apply(
            func,
            mni,
            list(ref_2_mni["fwd_transforms"]) + list(func_2_ref["fwd_transforms"]),
            list(ref_2_mni["fwd_which_to_invert"])
            + list(func_2_ref["fwd_which_to_invert"]),
            workspace,
            "handbuilt",
        )
        stacked_image = nib.load(stacked)
        handbuilt_image = nib.load(handbuilt)
        target_image = nib.load(mni)
        stacked_data = stacked_image.get_fdata()
        assert np.count_nonzero(stacked_data) > 100
        # geometry: the result lives on the reference grid, untouched
        assert stacked_image.shape == target_image.shape
        assert np.allclose(stacked_image.affine, target_image.affine)
        assert stacked_image.header.get_zooms() == target_image.header.get_zooms()
        assert np.allclose(stacked_data, handbuilt_image.get_fdata(), atol=1e-4)

        # 2. agreement with the SEQUENTIAL two-step apply -------------------- #
        # Not voxel-wise: the sequential reference interpolates twice and the
        # stack once, which blurs the edges of a binary phantom by ~1e-2. The
        # geometry is what must agree.
        in_ref = self._direct_apply(
            func,
            ref,
            func_2_ref["fwd_transforms"],
            func_2_ref["fwd_which_to_invert"],
            workspace,
            "step_func_2_ref",
        )
        sequential = self._direct_apply(
            in_ref,
            mni,
            ref_2_mni["fwd_transforms"],
            ref_2_mni["fwd_which_to_invert"],
            workspace,
            "step_ref_2_mni",
        )
        sequential_data = nib.load(sequential).get_fdata()
        stacked_centre = self._centre_of_mass(stacked_data)
        sequential_centre = self._centre_of_mass(sequential_data)
        stacked_offset = np.linalg.norm(stacked_centre - sequential_centre)
        assert stacked_offset < 0.1, stacked_offset
        assert np.corrcoef(stacked_data.ravel(), sequential_data.ravel())[0, 1] > 0.999

        # 3. NEGATIVE CONTROL: the reversed stack must be plainly wrong ------ #
        # Same production path, caller order flipped. If this passed the bounds
        # above, the guard would not be sensitive to the ordering mistake.
        reversed_stack = self._stacked_apply(
            sources, ["ref", "mni"], func, mni, workspace, "reversed", inverse=False
        )
        reversed_data = nib.load(reversed_stack).get_fdata()
        reversed_offset = np.linalg.norm(
            self._centre_of_mass(reversed_data) - sequential_centre
        )
        assert reversed_offset > 1.0, reversed_offset
        assert reversed_offset > 10 * stacked_offset
        assert not np.allclose(reversed_data, stacked_data, atol=1e-4)

    def test_stack_roundtrip_inverse_carries_the_invert_flags(
        self, workspace, make_nifti
    ):
        """The inverse stack (mni -> func) must invert the affines it reuses.

        ANTs writes only the forward affine, so both inverse lists carry it and
        their ``which_to_invert`` flags are ``True`` for those entries. If the
        flag merge were dropped or misaligned, antspyx would silently apply the
        matrices un-inverted -- the exact silent failure ``wire_transforms``
        guards for a single registration, here across a stack.
        """
        import numpy as np
        import nibabel as nib

        shape = (40, 40, 40)
        func = make_nifti("func.nii.gz", data=self._sphere(shape, (20, 20, 20), 7))
        ref = make_nifti("ref.nii.gz", data=self._sphere(shape, (24, 18, 20), 7))
        mni = make_nifti("mni.nii.gz", data=self._sphere(shape, (24, 18, 26), 9))

        func_2_ref = self._register(ref, func, "Rigid", workspace, "reg_func_2_ref")
        ref_2_mni = self._register(mni, ref, "SyN", workspace, "reg_ref_2_mni")

        # a lone affine inverse really is flagged for inversion
        assert func_2_ref["inv_which_to_invert"] == [True]
        assert any(ref_2_mni["inv_which_to_invert"])

        # mni -> func: output space is func, so the stack runs func->ref first
        sources = {
            "ref": (
                func_2_ref["inv_transforms"],
                func_2_ref["inv_which_to_invert"],
            ),
            "mni": (
                ref_2_mni["inv_transforms"],
                ref_2_mni["inv_which_to_invert"],
            ),
        }
        stacked = self._stacked_apply(
            sources, ["ref", "mni"], mni, func, workspace, "inverse", inverse=True
        )
        handbuilt = self._direct_apply(
            mni,
            func,
            list(func_2_ref["inv_transforms"]) + list(ref_2_mni["inv_transforms"]),
            list(func_2_ref["inv_which_to_invert"])
            + list(ref_2_mni["inv_which_to_invert"]),
            workspace,
            "handbuilt_inverse",
        )
        stacked_image = nib.load(stacked)
        stacked_data = stacked_image.get_fdata()
        func_image = nib.load(func)
        assert np.count_nonzero(stacked_data) > 100
        assert stacked_image.shape == func_image.shape
        assert np.allclose(stacked_image.affine, func_image.affine)
        assert np.allclose(stacked_data, nib.load(handbuilt).get_fdata(), atol=1e-4)

        # and the round trip lands back on the original func blob
        offset = np.linalg.norm(
            self._centre_of_mass(stacked_data)
            - self._centre_of_mass(func_image.get_fdata())
        )
        assert offset < 1.5, offset


# --------------------------------------------------------------------------- #
# C3 (Phase 3): the ANTS apply MapNode iterates the moving image
#
# The task/resting consumers apply a *list* of statistical maps through one
# node: ``apply_registration_node(..., iterfield=["in_file", "out_file"])``.
# ``in_file`` is the FSL/Synth name for the moving image; AntsApplyTransforms
# calls it ``input_image``, and a nipype MapNode silently ignores an iterfield
# its interface does not declare -- the whole list would then be handed to a
# single File input at run time. The abstraction therefore translates the name
# on the ANTS branch, next to the equivalent translation its connect calls do.
# --------------------------------------------------------------------------- #
class TestApplyRegistrationNodeIterfield:
    @staticmethod
    def _identity_wrapper(workflow, boundary):
        from swane.nipype_pipeline.nodes.utils import RegistrationNodeWrapper

        return RegistrationNodeWrapper(
            input_node=boundary,
            out_registered_node=boundary,
            warp="transforms",
            inv_warp_node=boundary,
            inv_warp="transforms",
            engine=RegistrationEngine.ANTS,
            fwd_transforms=[(boundary, "transforms")],
            inv_transforms=[(boundary, "transforms")],
            fwd_which_to_invert=(boundary, "flags"),
            inv_which_to_invert=(boundary, "flags"),
        )

    def _apply(self, engine, iterfield=("in_file", "out_file")):
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import apply_registration_node

        workflow = CustomWorkflow(name="wf")
        boundary = Node(
            IdentityInterface(
                fields=["moving", "reference", "transforms", "flags", "names"]
            ),
            name="boundary",
        )
        return apply_registration_node(
            name="maps",
            engine=engine,
            workflow=workflow,
            warp=[boundary, "transforms"],
            registration=self._identity_wrapper(workflow, boundary),
            moving=[boundary, "moving"],
            reference=[boundary, "reference"],
            out_file=[boundary, "names"],
            non_linear=False,
            iterfield=list(iterfield),
        )

    def test_ants_translates_in_file_iterfield(self):
        node = self._apply(RegistrationEngine.ANTS)
        assert _iface(node) == "AntsApplyTransforms"
        assert node.iterfield == ["input_image", "out_file"]

    def test_fsl_iterfield_is_left_alone(self):
        node = self._apply(RegistrationEngine.FSL)
        assert _iface(node) == "ApplyXFM"
        assert node.iterfield == ["in_file", "out_file"]

    def test_caller_may_use_the_ants_name_directly(self):
        """Translation only renames ``in_file``; anything else passes through."""
        node = self._apply(RegistrationEngine.ANTS, iterfield=("input_image",))
        assert node.iterfield == ["input_image"]


@pytest.mark.heavy
class TestAntsApplyIterfieldRun:
    """Runtime guard for the translation above: the MapNode must really resample
    each moving image on its own. An identity affine keeps the expensive part
    out -- what is under test is the iteration, not the resampling maths."""

    @staticmethod
    def _identity_transform(path):
        import ants

        ants.write_transform(
            ants.create_ants_transform(transform_type="AffineTransform", dimension=3),
            str(path),
        )
        return str(path)

    def test_each_moving_image_is_resampled_separately(self, workspace, make_nifti):
        import glob
        import os

        import nibabel as nib
        import numpy as np
        from nipype.interfaces.utility import IdentityInterface
        from swane.nipype_pipeline.nodes.utils import (
            RegistrationNodeWrapper,
            apply_registration_node,
        )

        reference = make_nifti("reference.nii.gz", shape=(8, 8, 8))
        first = np.zeros((8, 8, 8), dtype=np.float32)
        first[2, 2, 2] = 1.0
        second = np.zeros((8, 8, 8), dtype=np.float32)
        second[5, 5, 5] = 1.0
        movings = [
            make_nifti("map1.nii.gz", data=first),
            make_nifti("map2.nii.gz", data=second),
        ]
        transform = self._identity_transform(workspace / "identity.mat")

        run_dir = str(workspace / "iterfield_run")
        workflow = CustomWorkflow(name="iterfield")
        workflow.base_dir = run_dir
        boundary = Node(
            IdentityInterface(
                fields=["moving", "reference", "transforms", "flags", "names"]
            ),
            name="boundary",
        )
        boundary.inputs.moving = movings
        boundary.inputs.reference = reference
        boundary.inputs.transforms = [transform]
        boundary.inputs.flags = [False]
        boundary.inputs.names = ["r-map1.nii.gz", "r-map2.nii.gz"]
        apply_registration_node(
            name="maps",
            engine=RegistrationEngine.ANTS,
            workflow=workflow,
            warp=[boundary, "transforms"],
            registration=RegistrationNodeWrapper(
                input_node=boundary,
                out_registered_node=boundary,
                warp="transforms",
                inv_warp_node=boundary,
                inv_warp="transforms",
                engine=RegistrationEngine.ANTS,
                fwd_transforms=[(boundary, "transforms")],
                inv_transforms=[(boundary, "transforms")],
                fwd_which_to_invert=(boundary, "flags"),
                inv_which_to_invert=(boundary, "flags"),
            ),
            moving=[boundary, "moving"],
            reference=[boundary, "reference"],
            out_file=[boundary, "names"],
            non_linear=False,
            iterfield=["in_file", "out_file"],
        )
        workflow.run()
        os.chdir(str(workspace))

        # One output per moving image, each carrying its own peak: proof the
        # MapNode iterated instead of collapsing the list onto one apply.
        for name, expected_peak in (
            ("r-map1.nii.gz", (2, 2, 2)),
            ("r-map2.nii.gz", (5, 5, 5)),
        ):
            matches = glob.glob(os.path.join(run_dir, "**", name), recursive=True)
            assert matches, "the MapNode produced no %s" % name
            data = nib.load(matches[0]).get_fdata()
            assert np.unravel_index(int(np.argmax(data)), data.shape) == expected_peak
