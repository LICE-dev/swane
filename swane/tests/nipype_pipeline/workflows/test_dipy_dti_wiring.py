"""Wiring assertions for
:func:`swane.nipype_pipeline.workflows.dipy_dti_preproc_workflow.dipy_dti_preproc_workflow`.

These are graph-shape checks (independent of the golden byte snapshots, which
Task 9 owns): the pipeline nodes are present and connected in the spec-section-5
order, the four boundary outputs Phase 2 depends on are advertised, seeding is
restricted to the WM PVE mask, the three PVE maps reach the tracking node (which
hosts both the seeding and the CMC stopping criterion), the reference image is
wired into tracking, and -- following spec section 1 -- the abstracted
registration step honours the user's global engine choice (ANTs or FSL), which
in turn drives the format the diff->ref affine is read from.
"""

import pytest

from swane.config.config_enums import (
    GlobalPrefCategoryList,
    DeskullEngine,
    DeskullModality,
    RegistrationEngine,
    TractographyEngine,
)
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.dipy_dti_preproc_workflow import (
    dipy_dti_preproc_workflow,
)


# --------------------------------------------------------------------------- #
# Helpers mirroring test_dti_matrix.py.
# --------------------------------------------------------------------------- #
def _iface(node):
    return type(node.interface).__name__


def _iface_module(node):
    return type(node.interface).__module__


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _node_by_name(wf, name):
    return next(n for n in wf._graph.nodes() if n.name == name)


def _node_by_prefix(wf, prefix):
    return next(n for n in wf._graph.nodes() if n.name.startswith(prefix))


MAX_CPU = 4


@pytest.fixture
def build_dipy_wf(subject_config, global_config, make_input_dir):
    """Build the workflow with an optional registration engine / core budget.

    A non-FSL deskull engine keeps the shared head FSL-free; the registration
    engine follows the SYNTH ``engine`` preference (spec section 1), defaulting
    to ANTs when unset.
    """

    def _build(engine=None, max_cpu=MAX_CPU):
        section = subject_config[DataInputList.DTI]
        section["tractography"] = "true"
        synth = global_config[GlobalPrefCategoryList.SYNTH]
        synth["tractography_engine"] = TractographyEngine.DIPY_RECOBUNDLES.name
        synth["deskull_engine"] = DeskullEngine.ANTSPYNET.name
        if engine is not None:
            synth["engine"] = engine.name
        return dipy_dti_preproc_workflow(
            "dti",
            dti_dir=make_input_dir(),
            config=section,
            synth_config=synth,
            deskull_modality=DeskullModality.NODIF,
            max_cpu=max_cpu,
        )

    return _build


@pytest.fixture
def dipy_wf(build_dipy_wf):
    return build_dipy_wf()


class TestNodePresence:
    def test_pipeline_nodes_present(self, dipy_wf):
        names = {n.name for n in dipy_wf._graph.nodes()}
        for expected in (
            "dipy_conv",
            "dipy_reOrient",
            "dipy_nodif",
            "dipy_denoise",
            "dipy_motion",
            "dipy_bias",
            "dipy_tensorfit",
            "dipy_csd",
            "dipy_tissue",
            "dipy_tracking",
            "dipy_slr",
            "dif2ref_antsreg",
            "dif2ref_to_ras",
        ):
            assert expected in names, expected
        # the deskull node carries an engine-specific suffix
        assert any(n.startswith("dipy_deskull") for n in names)

    def test_outputnode_advertises_the_four_boundary_fields(self, dipy_wf):
        outputnode = _node_by_name(dipy_wf, "outputnode")
        fields = set(outputnode.interface._fields)
        assert {"FA", "tractogram", "tractogram_atlas", "atlas2native"} <= fields


class TestRegistrationEngine:
    """The abstracted registration step follows the user's global engine choice
    (spec section 1), which drives the interface built and the format the
    diff->ref affine is read from. The dipy engine's own steps stay FSL-free;
    it never uses AffineToFSL (its tracker consumes a plain RAS affine)."""

    @pytest.mark.parametrize(
        "engine,reg_iface,ras_fmt",
        [
            (RegistrationEngine.ANTS, "AntsRegistration", "itk"),
            (RegistrationEngine.FSL, "FLIRT", "fsl"),
        ],
        ids=["ants", "fsl"],
    )
    def test_registration_follows_global_engine(
        self, build_dipy_wf, engine, reg_iface, ras_fmt
    ):
        wf = build_dipy_wf(engine=engine)
        ifaces = {_iface(n) for n in wf._graph.nodes()}
        assert reg_iface in ifaces
        assert "AffineToRAS" in ifaces
        assert "AffineToFSL" not in ifaces
        ras = _node_by_name(wf, "dif2ref_to_ras")
        assert ras.inputs.in_fmt == ras_fmt

    def test_fsl_engine_uses_no_ants_registration(self, build_dipy_wf):
        wf = build_dipy_wf(engine=RegistrationEngine.FSL)
        ifaces = {_iface(n) for n in wf._graph.nodes()}
        assert "AntsRegistration" not in ifaces


class TestParallelCoreReservation:
    """n_procs is left to nipype's num_threads-derived default: the nodes whose
    interface exposes ``num_threads`` carry no explicit n_procs, yet must still
    reserve the per-node core budget."""

    @pytest.mark.parametrize(
        "node_name",
        ["dipy_denoise", "dipy_motion", "dipy_bias", "dipy_csd", "dipy_tracking"],
    )
    def test_num_threads_nodes_reserve_the_core_budget(self, dipy_wf, node_name):
        node = _node_by_name(dipy_wf, node_name)
        assert node.inputs.num_threads == MAX_CPU
        assert node.n_procs == MAX_CPU

    def test_slr_reserves_a_single_core(self, dipy_wf):
        slr = _node_by_name(dipy_wf, "dipy_slr")
        assert slr.inputs.num_threads == 1
        assert slr.n_procs == 1


class TestMaxCpuZeroClamp:
    """max_cpu==0 means 'auto/all cores'; propagated raw it reads downstream as
    'all cores', so it must reach the abstracted deskull and registration nodes
    clamped to 1 (spec section 10 / the dipy nodes' parallel_cpu guard)."""

    def test_deskull_and_registration_clamp_zero_to_one(self, build_dipy_wf):
        wf = build_dipy_wf(max_cpu=0)
        deskull = _node_by_prefix(wf, "dipy_deskull")
        reg = _node_by_name(wf, "dif2ref_antsreg")
        assert deskull.inputs.num_threads == 1
        assert deskull.n_procs == 1
        assert reg.inputs.num_threads == 1
        assert reg.n_procs == 1


class TestDwiChainOrder:
    """denoise -> motion -> bias -> tensorfit (spec section 5)."""

    def test_chain(self, dipy_wf):
        reorient = _node_by_name(dipy_wf, "dipy_reOrient")
        conv = _node_by_name(dipy_wf, "dipy_conv")
        denoise = _node_by_name(dipy_wf, "dipy_denoise")
        motion = _node_by_name(dipy_wf, "dipy_motion")
        bias = _node_by_name(dipy_wf, "dipy_bias")
        tensorfit = _node_by_name(dipy_wf, "dipy_tensorfit")
        deskull = _node_by_prefix(dipy_wf, "dipy_deskull")

        assert (reorient, "out_file", "in_file") in _incoming(dipy_wf, denoise)
        assert (conv, "bvals", "bval") in _incoming(dipy_wf, denoise)
        assert (denoise, "out_file", "in_file") in _incoming(dipy_wf, motion)
        assert (motion, "out_file", "in_file") in _incoming(dipy_wf, bias)

        tf_inc = _incoming(dipy_wf, tensorfit)
        assert (bias, "out_file", "in_file") in tf_inc
        assert (motion, "out_bvec", "bvec") in tf_inc
        assert (motion, "out_bval", "bval") in tf_inc
        assert (deskull, "mask_file", "mask") in tf_inc

    def test_fa_reaches_outputnode_via_ants_apply(self, dipy_wf):
        outputnode = _node_by_name(dipy_wf, "outputnode")
        fa_apply = _node_by_name(dipy_wf, "fa_2_ref_ants_apply")
        assert _iface(fa_apply) == "AntsApplyTransforms"
        assert (fa_apply, "out_file", "FA") in _incoming(dipy_wf, outputnode)


class TestTissueBranchAndTracking:
    def test_pve_maps_resampled_ref_to_diff_and_reach_tracking(self, dipy_wf):
        tissue = _node_by_name(dipy_wf, "dipy_tissue")
        tracking = _node_by_name(dipy_wf, "dipy_tracking")
        track_inc = _incoming(dipy_wf, tracking)

        for tissue_field, apply_name, track_field in (
            ("pve_wm", "pve_wm_2_diff_ants_apply", "pve_wm"),
            ("pve_gm", "pve_gm_2_diff_ants_apply", "pve_gm"),
            ("pve_csf", "pve_csf_2_diff_ants_apply", "pve_csf"),
        ):
            apply_node = _node_by_name(dipy_wf, apply_name)
            # tissue classifier PVE -> ref->diff ANTs resample
            assert (tissue, tissue_field, "input_image") in _incoming(
                dipy_wf, apply_node
            )
            # resampled PVE -> tracking (seeding for WM, CMC for all three)
            assert (apply_node, "out_file", track_field) in track_inc

    def test_tissue_classifier_runs_on_reference_brain(self, dipy_wf):
        tissue = _node_by_name(dipy_wf, "dipy_tissue")
        inputnode = _node_by_name(dipy_wf, "inputnode")
        assert (inputnode, "reference_brain", "in_file") in _incoming(dipy_wf, tissue)

    def test_wm_seed_mask_is_wired_not_whole_brain(self, dipy_wf):
        """Seeding is the WM PVE channel: the WM apply node feeds tracking's
        ``pve_wm`` (the seed mask), and no whole-brain mask is wired in its
        place."""
        tracking = _node_by_name(dipy_wf, "dipy_tracking")
        wm_apply = _node_by_name(dipy_wf, "pve_wm_2_diff_ants_apply")
        assert (wm_apply, "out_file", "pve_wm") in _incoming(dipy_wf, tracking)

    def test_tracking_consumes_csd_reference_and_ras_affine(self, dipy_wf):
        tracking = _node_by_name(dipy_wf, "dipy_tracking")
        csd = _node_by_name(dipy_wf, "dipy_csd")
        inputnode = _node_by_name(dipy_wf, "inputnode")
        ras = _node_by_name(dipy_wf, "dif2ref_to_ras")
        inc = _incoming(dipy_wf, tracking)
        assert (csd, "shm_coeff", "shm_coeff") in inc
        # a StatefulTractogram needs the reference image, not just the affine
        assert (inputnode, "reference", "reference") in inc
        assert (ras, "out_ras", "affine_diff2ref") in inc

    def test_tracking_params_follow_preferences(self, dipy_wf):
        tracking = _node_by_name(dipy_wf, "dipy_tracking")
        assert tracking.inputs.seed_density == 2
        assert tracking.inputs.max_angle == 20.0
        assert tracking.inputs.step_size == 0.2


class TestAtlasSlrOnceAndBoundaryOutputs:
    def test_tractogram_and_slr_outputs_reach_outputnode(self, dipy_wf):
        outputnode = _node_by_name(dipy_wf, "outputnode")
        tracking = _node_by_name(dipy_wf, "dipy_tracking")
        slr = _node_by_name(dipy_wf, "dipy_slr")
        inc = _incoming(dipy_wf, outputnode)

        assert (tracking, "tractogram", "tractogram") in inc
        # SLR runs once, off the native-space tractogram
        assert (tracking, "tractogram", "tractogram") in _incoming(dipy_wf, slr)
        assert (slr, "tractogram_atlas", "tractogram_atlas") in inc
        assert (slr, "atlas2native", "atlas2native") in inc

    def test_only_one_slr_node(self, dipy_wf):
        slr_nodes = [n for n in dipy_wf._graph.nodes() if _iface(n) == "DipyAtlasSLR"]
        assert len(slr_nodes) == 1


class TestRasAffineWiring:
    def test_ras_node_bridges_ants_forward_transform(self, dipy_wf):
        ras = _node_by_name(dipy_wf, "dif2ref_to_ras")
        ants_reg = _node_by_name(dipy_wf, "dif2ref_antsreg")
        inputnode = _node_by_name(dipy_wf, "inputnode")
        deskull = _node_by_prefix(dipy_wf, "dipy_deskull")
        inc = _incoming(dipy_wf, ras)
        assert (ants_reg, "fwd_transforms", "in_transform") in inc
        assert (deskull, "out_file", "source_file") in inc
        assert (inputnode, "reference_brain", "reference_file") in inc
