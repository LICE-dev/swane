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
