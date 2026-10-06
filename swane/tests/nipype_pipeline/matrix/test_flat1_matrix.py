"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.flat1_workflow.flat1_workflow`.

FLAT1 junction/extension z-score pipeline. It references packaged
``swane.resources`` templates (rewritten to ``<RESOURCES>`` in snapshots) and
an MNI template path that only needs to exist. Snapshots under
``snapshots/flat1/``.

Phase 2 (CP-E) lifted this workflow's Phase-1 FSL pin: it now resolves its
engine with ``allow_ants=True``. Its 7 nonlinear applies already passed
``warp=[inputnode, "<field>"]``, ``registration=None`` -- the composed-field
single-file ANTS path built by Session C -- so no wiring changed here. The
FSL/SynthMorph snapshots below are pinned explicitly and stay byte-identical.
Session G (CP-G) added the ``ants_backend`` scenario as the golden
ANTS-default snapshot, eye-reviewed alongside the pre-existing node/edge
construction test (``test_flat1_ants_construction``), which keeps asserting
the graph SHAPE independently of the byte snapshot.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

flat1_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.flat1_workflow", "flat1_workflow"
)

SUBDIR = "flat1"

SCENARIOS = {
    "fsl_backend": "FSL",
    "synthmorph_backend": "SYNTH",
    "ants_backend": "ANTS",
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_flat1_matrix(scenario, global_config, make_file, graph_snapshot):
    engine = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "true" if engine == "SYNTH" else "false"
    synth["engine"] = engine
    synth["segmentation_engine"] = "FSL"

    wf = flat1_workflow(
        "flat1",
        mni1_dir=make_file("mni1.nii.gz", "x"),
        synth_config=synth,
    )

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config={"synth_morph": synth["morph"], "registration_engine": engine},
        title="flat1 / %s" % scenario,
    )


# --------------------------------------------------------------------------- #
# ANTS-default construction (node/edge assertions, independent of the
# ``ants_backend`` byte snapshot above): the 7 nonlinear applies (4 forward via
# ref_2_mni1_warp, 3 inverse via ref_2_mni1_inverse_warp) become
# AntsApplyTransforms fed the composed boundary field through a Merge(1), with
# no which_to_invert (the composition already baked the direction in).
# --------------------------------------------------------------------------- #
def _iface(node):
    return type(node.interface).__name__


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _build(global_config, make_file, engine):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine
    synth["segmentation_engine"] = "FSL"
    return flat1_workflow(
        "flat1",
        mni1_dir=make_file("mni1.nii.gz", "x"),
        synth_config=synth,
    )


def test_flat1_ants_construction(global_config, make_file):
    from nipype.interfaces.base import isdefined

    wf = _build(global_config, make_file, "ANTS")
    ants_applies = [n for n in wf._graph.nodes() if _iface(n) == "AntsApplyTransforms"]
    assert len(ants_applies) == 7
    # the pin is truly lifted: no FSL/Synth apply nodes remain
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ApplyWarp" not in ifaces and "SynthMorphApply" not in ifaces

    forward_field = {"ref_2_mni1_warp": 0, "ref_2_mni1_inverse_warp": 0}
    for node in ants_applies:
        assert not isdefined(node.inputs.which_to_invert)
        incoming = _incoming(wf, node)
        tl = [c for c in incoming if c[2] == "transformlist"]
        assert len(tl) == 1
        merge_node, merge_field, _ = tl[0]
        assert _iface(merge_node) == "Merge"
        merge_in = _incoming(wf, merge_node)
        assert len(merge_in) == 1
        src, src_field, _ = merge_in[0]
        assert src.name == "inputnode"
        assert src_field in forward_field
        forward_field[src_field] += 1

    assert forward_field["ref_2_mni1_warp"] == 4
    assert forward_field["ref_2_mni1_inverse_warp"] == 3


def test_flat1_fsl_construction_unchanged(global_config, make_file):
    """The pin lift must not disturb the FSL graph: 7 ApplyWarp, no ANTs."""
    wf = _build(global_config, make_file, "FSL")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("ApplyWarp") == 7
    assert "AntsApplyTransforms" not in ifaces


# --------------------------------------------------------------------------- #
# Segmentation-engine axis (independent of the registration axis above): the
# tissue segmentation itself runs once in ref_workflow (``ref_segmentation``)
# and reaches FLAT1 through ``inputnode.tissue_pve`` / ``tissue_restored``, so
# FLAT1 builds no segmentation node for either engine. The engine still
# selects the 0.1 posterior threshold applied to the dense Atropos posteriors
# before they are used as GM/WM masks (FSL FAST PVE are used directly).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("segmentation", ["ANTS", "FSL"])
def test_flat1_consumes_shared_segmentation(global_config, make_file, segmentation):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"  # isolate the segmentation change
    synth["segmentation_engine"] = segmentation
    wf = flat1_workflow(
        "flat1", mni1_dir=make_file("mni1.nii.gz", "x"), synth_config=synth
    )
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "AntsAtropos" not in ifaces and "FAST" not in ifaces

    node_by_name = {n.name: n for n in wf._graph.nodes()}
    assert "flat1_atropos" not in node_by_name and "flat1_fast" not in node_by_name
    inputnode = node_by_name["inputnode"]
    assert {"tissue_pve", "tissue_restored"} <= set(inputnode.interface._fields)

    # split node fed by the shared [CSF, GM, WM] tissue maps
    split_in = _incoming(wf, node_by_name["fast_segment_split"])
    assert split_in == [(inputnode, "tissue_pve", "file_list")]
    # restore_2_mni1 moves the shared restored (bias-corrected) T1.
    # The FSL apply node names itself "<name>_apply_warp" (non_linear ApplyWarp).
    restore_in = _incoming(wf, node_by_name["restore_2_mni1_apply_warp"])
    assert (inputnode, "tissue_restored", "in_file") in restore_in

    # dense Atropos posteriors are thresholded at 0.1; FAST PVE are not
    thresholds = {"flat1_gm_bin", "flat1_wm_bin"}
    if segmentation == "ANTS":
        assert thresholds <= set(node_by_name)
        for thr in thresholds:
            assert node_by_name[thr].inputs.thresh == 0.1
    else:
        assert not thresholds & set(node_by_name)


def test_flat1_atropos_matrix(global_config, make_file, graph_snapshot):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["morph"] = "false"
    synth["engine"] = "FSL"  # isolate the segmentation change
    synth["segmentation_engine"] = "ANTS"
    wf = flat1_workflow(
        "flat1",
        mni1_dir=make_file("mni1.nii.gz", "x"),
        synth_config=synth,
    )
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="atropos_backend",
        config={"segmentation_engine": "ANTS"},
        title="flat1 / atropos_backend",
    )
