"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.tractography_workflow.tractography_workflow`.

The baseline is a fully-equipped FSL install: with the XTRACT protocol data
present (``$FSLDIR/data/xtract_data/.../<tract>_l|_r``) the builder assembles
the real per-hemisphere probtrackx graph, which is what we snapshot. On a box
without that data the *known-tract* scenario degrades to a skip (never a
failure). The *unknown-tract* scenario is genuinely tool-independent — a name
that is not in ``TRACTS`` always returns ``None`` regardless of what is
installed — so it is asserted directly. Snapshots under ``snapshots/tractography/``.

Phase 2 (CP-E) lifted this workflow's Phase-1 FSL pin: it now resolves its
engine with ``allow_ants=True``. Fixing this pin lift also surfaced a real
bug: for a tract with exactly one target ROI (e.g. ``cst``), the builder set
``targets_2_ref.inputs.in_file`` directly -- FSL/Synth's moving-image field
name -- which does not exist on ``AntsApplyTransforms`` (its moving-image
field is ``input_image``); the multi-target ``.iterables`` path had the same
FSL-specific field name baked in. Both now resolve the field name from the
engine. The seed/exclude applies already passed ``moving=<path>`` through
``apply_registration_node`` itself, so those needed no change. The FSL
snapshots below are pinned explicitly and stay byte-identical; the
ANTS-default golden snapshot is (re)generated and eye-reviewed in Session G.
Until then, the ANTS graph is covered here by an explicit node/edge
construction test (``test_tractography_ants_construction``), not by a byte
snapshot.
"""

import os

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.config.preference_list import XTRACT_DATA_DIR
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

tractography_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.tractography_workflow", "tractography_workflow"
)
from swane.tests.nipype_pipeline.matrix.conftest import require_fsl_data

SUBDIR = "tractography"


def test_unknown_tract_returns_none(subject_config, global_config):
    """A tract name not in ``TRACTS`` is rejected before any FSL data is read."""
    wf = tractography_workflow(
        "definitely_not_a_tract",
        config=subject_config[DataInputList.DTI],
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )
    assert wf is None, "an unknown tract name must return None on any box"


def test_known_tract_real_graph(subject_config, global_config, graph_snapshot):
    """With XTRACT data present (the norm), the real cst graph is built and snapshotted."""
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # tractography is not yet exercised under ANTS in this matrix; pin FSL so
    # this scenario keeps matching its existing golden snapshot.
    synth["engine"] = "FSL"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=synth,
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph",
        config={"tract": "cst", "cuda": "false", "xtract_data": "present"},
        title="tractography / cst_real_graph",
    )


def test_known_tract_real_graph_test_run(subject_config, global_config, graph_snapshot):
    """test_run=True: n_samples is halved from the xtract-protocol value.
    Unvalidated end-to-end yet -- see prerelease/TODO.md.
    """
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # tractography is not yet exercised under ANTS in this matrix; pin FSL so
    # this scenario keeps matching its existing golden snapshot.
    synth["engine"] = "FSL"

    wf = tractography_workflow(
        "cst",
        config=section,
        synth_config=synth,
        test_run=True,
    )
    assert wf is not None, "cst graph should build when XTRACT data is present"

    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="cst_real_graph_test_run",
        config={
            "tract": "cst",
            "cuda": "false",
            "xtract_data": "present",
            "test_run": True,
        },
        title="tractography / cst_real_graph_test_run",
    )


# --------------------------------------------------------------------------- #
# CP-E: ANTS-default construction (node/edge assertions, not byte snapshot).
#
# The "cst" protocol has exactly one target ROI (target.nii.gz) and an
# exclude ROI (exclude.nii.gz), no stop/invert -- so it exercises the
# single-target-file branch that carried the FSL-specific ``in_file`` bug.
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


def test_tractography_ants_construction(subject_config, global_config):
    from nipype.interfaces.base import isdefined

    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "ANTS"

    wf = tractography_workflow("cst", config=section, synth_config=synth)
    assert wf is not None

    ants_applies = [n for n in wf._graph.nodes() if _iface(n) == "AntsApplyTransforms"]
    # seed_2_ref + targets_2_ref + exclude_2_ref, per side (lh, rh)
    assert len(ants_applies) == 6
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert "ApplyWarp" not in ifaces

    inputnode = next(n for n in wf._graph.nodes() if n.name == "inputnode")
    for node in ants_applies:
        # every nonlinear-warp apply in this workflow is a labelmap resample
        assert node.inputs.interpolator == "nearestNeighbor"
        assert not isdefined(node.inputs.which_to_invert)
        incoming = _incoming(wf, node)
        tl = [c for c in incoming if c[2] == "transformlist"]
        assert len(tl) == 1
        merge_node, merge_field, _ = tl[0]
        assert _iface(merge_node) == "Merge"
        merge_in = _incoming(wf, merge_node)
        assert len(merge_in) == 1
        src, src_field, _ = merge_in[0]
        assert src is inputnode
        assert src_field == "mni2ref_warp"

    # the single-target-file fix: targets_2_ref's moving image is set on
    # AntsApplyTransforms' real field name (input_image), not FSL's in_file.
    targets_2_ref_nodes = [n for n in ants_applies if "targets_2_ref" in n.name]
    assert len(targets_2_ref_nodes) == 2
    for node in targets_2_ref_nodes:
        assert isdefined(node.inputs.input_image)
        # AntsApplyTransforms has no in_file trait at all -- the FSL-specific
        # field name from the pre-fix bug must not have been (re)added.
        assert not hasattr(node.inputs, "in_file")


def test_tractography_fsl_construction_unchanged(subject_config, global_config):
    """The pin lift must not disturb the FSL graph: ApplyWarp, no ANTs."""
    require_fsl_data(os.path.join(XTRACT_DATA_DIR, "cst_l"))

    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"

    wf = tractography_workflow("cst", config=section, synth_config=synth)
    assert wf is not None

    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("ApplyWarp") == 6
    assert "AntsApplyTransforms" not in ifaces

    targets_2_ref_nodes = [n for n in wf._graph.nodes() if "targets_2_ref" in n.name]
    assert len(targets_2_ref_nodes) == 2
    for node in targets_2_ref_nodes:
        assert node.inputs.in_file
