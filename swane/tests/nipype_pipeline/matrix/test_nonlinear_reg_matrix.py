"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.nonlinear_reg_workflow.nonlinear_reg_workflow`.

Non-linear atlas registration (used for the FLAT1 MNI warp and the symmetric
asymmetry-index warp). One snapshot per backend under
``snapshots/nonlinear_reg/``.

Phase 2 (CP-D) lifted this workflow's Phase-1 FSL pin: it now resolves its
engine with ``allow_ants=True`` and follows the configured engine like
``linear_reg_workflow``. Under ANTS it emits its ``fieldcoeff_file`` /
``inverse_warp`` boundary outputs as single composed displacement fields (two
``AntsComposeTransform`` nodes), so the field names/cardinality downstream stay
1:1. The FSL/SYNTH snapshots below are unchanged (those branches are
byte-identical). Session G (CP-G) added the ``ants_backend`` scenario as the
golden ANTS-default snapshot, eye-reviewed alongside the pre-existing
node/edge construction test (``test_nonlinear_reg_ants_construction``), which
keeps asserting the graph SHAPE independently of the byte snapshot.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, CoreLimit
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

nonlinear_reg_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.nonlinear_reg_workflow", "nonlinear_reg_workflow"
)

SUBDIR = "nonlinear_reg"
MAX_CPU = 4

# name -> dict(engine preference + limit_cores)
# The ANTS default is covered by test_nonlinear_reg_ants_construction (node/edge
# assertions) until Session G regenerates the golden ANTS snapshot; the FSL/SYNTH
# byte snapshots below are unchanged by the CP-D pin lift.
SCENARIOS = {
    "fsl_backend": dict(engine="FSL"),
    "synthmorph_backend": dict(engine="SYNTH"),
    "synthmorph_backend_limit_cores": dict(engine="SYNTH", limit_cores=True),
    "ants_backend": dict(engine="ANTS"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_nonlinear_reg_matrix(scenario, global_config, graph_snapshot):
    params = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # ``morph`` is gone; pin the backend through the ``engine`` enum (``morph``
    # kept only so the snapshot header echo stays identical).
    synth["morph"] = "true" if params["engine"] == "SYNTH" else "false"
    synth["engine"] = params["engine"]
    synth["limit_cores"] = "true" if params.get("limit_cores") else "false"

    wf = nonlinear_reg_workflow(
        "sym",
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={
            "synth_morph": synth["morph"],
            "registration_engine": synth["engine"],
            "limit_synth_cores": synth["limit_cores"],
            "max_cpu": MAX_CPU,
            "multicore_node_limit": CoreLimit.SOFT_CAP.name,
        },
        title="nonlinear_reg / %s" % scenario,
    )


TEST_RUN_SCENARIOS = {
    "fsl_backend_test_run": False,
    "synthmorph_backend_test_run": True,
}


@pytest.mark.parametrize(
    "scenario", list(TEST_RUN_SCENARIOS), ids=list(TEST_RUN_SCENARIOS)
)
def test_nonlinear_reg_matrix_test_run(scenario, global_config, graph_snapshot):
    """test_run=True on both backends: FNIRT/InvWarp strategy A (FSL) and
    SynthMorphReg steps=5 (Synth) -- this is the shared registration used by
    sym/mni1, which prerelease's default test_run=True actually builds.
    """
    synth_morph = TEST_RUN_SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if synth_morph else "false"
    synth["engine"] = "SYNTH" if synth_morph else "FSL"

    wf = nonlinear_reg_workflow(
        "sym",
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
        test_run=True,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={
            "synth_morph": synth["morph"],
            "max_cpu": MAX_CPU,
            "multicore_node_limit": CoreLimit.SOFT_CAP.name,
            "test_run": True,
        },
        title="nonlinear_reg / %s" % scenario,
    )


# --------------------------------------------------------------------------- #
# ANTS-default construction (node/edge assertions, independent of the
# ``ants_backend`` byte snapshot above): an AntsRegistration plus two
# AntsComposeTransform nodes composing the ordered transform list (+ its
# which_to_invert) into the single fieldcoeff_file / inverse_warp boundary
# fields, with the forward composed on the atlas grid and the inverse on the
# in_file grid. Field names/cardinality on outputnode are unchanged.
# --------------------------------------------------------------------------- #
def _iface(node):
    return type(node.interface).__name__


def _node(wf, name):
    for n in wf._graph.nodes():
        if n.name == name:
            return n
    raise AssertionError("no node named %r in %s" % (name, wf.name))


def _incoming(wf, dst_node):
    """(src_node, src_field, dst_field) edges feeding ``dst_node``."""
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _build(global_config, engine):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if engine == "SYNTH" else "false"
    synth["engine"] = engine
    synth["limit_cores"] = "false"
    return nonlinear_reg_workflow(
        "sym",
        synth_config=synth,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )


def test_nonlinear_reg_ants_construction(global_config):
    wf = _build(global_config, "ANTS")
    ifaces = sorted(_iface(n) for n in wf._graph.nodes())

    # exactly one registration node and the two boundary composers
    assert ifaces.count("AntsRegistration") == 1
    assert ifaces.count("AntsComposeTransform") == 2
    # the pin is truly lifted: no FSL registration nodes remain
    assert "FLIRT" not in ifaces and "FNIRT" not in ifaces and "InvWarp" not in ifaces

    ants_reg = next(n for n in wf._graph.nodes() if _iface(n) == "AntsRegistration")
    inputnode = _node(wf, "inputnode")
    outputnode = _node(wf, "outputnode")

    # fieldcoeff_file / inverse_warp are fed from the compose nodes, NOT straight
    # from the registration's list outputs.
    out_edges = _incoming(wf, outputnode)
    fwd_src = next(s for s, sf, df in out_edges if df == "fieldcoeff_file")
    inv_src = next(s for s, sf, df in out_edges if df == "inverse_warp")
    assert _iface(fwd_src) == "AntsComposeTransform"
    assert _iface(inv_src) == "AntsComposeTransform"
    assert fwd_src is not inv_src
    # the composed out_field is what crosses the boundary
    assert any(
        s is fwd_src and sf == "out_field" and df == "fieldcoeff_file"
        for s, sf, df in out_edges
    )
    assert any(
        s is inv_src and sf == "out_field" and df == "inverse_warp"
        for s, sf, df in out_edges
    )

    # forward composer: reference=atlas, transformlist+flags from the registration
    fwd_in = _incoming(wf, fwd_src)
    assert (inputnode, "atlas", "reference_image") in fwd_in
    assert (ants_reg, "fwd_transforms", "transformlist") in fwd_in
    assert (ants_reg, "fwd_which_to_invert", "which_to_invert") in fwd_in

    # inverse composer: reference=in_file, inverse transformlist+flags
    inv_in = _incoming(wf, inv_src)
    assert (inputnode, "in_file", "reference_image") in inv_in
    assert (ants_reg, "inv_transforms", "transformlist") in inv_in
    assert (ants_reg, "inv_which_to_invert", "which_to_invert") in inv_in

    # warped_file is still produced by the unbetted->atlas apply (unchanged path)
    warped_src = next(s for s, sf, df in out_edges if df == "warped_file")
    assert _iface(warped_src) == "AntsApplyTransforms"


def test_nonlinear_reg_fsl_construction_unchanged(global_config):
    """The pin lift must not disturb the FSL graph: FLIRT+FNIRT+InvWarp, no ANTs."""
    wf = _build(global_config, "FSL")
    ifaces = sorted(_iface(n) for n in wf._graph.nodes())
    assert ifaces.count("FLIRT") == 1
    assert ifaces.count("FNIRT") == 1
    assert ifaces.count("InvWarp") == 1
    assert "AntsRegistration" not in ifaces
    assert "AntsComposeTransform" not in ifaces
