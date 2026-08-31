"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.func_map_workflow.func_map_workflow`.

The ASL/PET functional-map builder is gated on two axes: the FreeSurfer step
(no FreeSurfer / parcellation-only SYNTHSEG / full RECONALL surfaces) and the
asymmetry-index (``ai``) preference. Each combination gets a golden snapshot
under ``snapshots/func_map/``. The builder itself has no ASL/PET branching, but
the two inputs have separate preference sections with a different default
``cost_func`` (see ``preference_list.py``: ASL -> NORMALIZED_MUTUAL_INFORMATION,
PET -> MUTUAL_INFORMATION) — ``pet_reconall_ai`` builds from
``DataInputList.PET``'s own section so that default is actually exercised
rather than assumed identical to ASL's.

Phase 2 (CP-E) lifted this workflow's Phase-1 FSL pin: it now resolves its
engine with ``allow_ants=True``. Fixing this pin lift also surfaced a real
bug: ``smooth_2_ref`` (the func->reference linear apply) reused the
in-workflow ``reg_wrap`` without passing ``registration=reg_wrap``, so under
ANTS it would have fed the apply node's ``transformlist`` through the
boundary-only ``Merge(1)`` path with no ``which_to_invert`` -- wrong for a
same-workflow registration reuse (see ``linear_reg_workflow``'s
``unbetted_2_ref``/``deskull_2_ref`` for the established pattern: ``warp=``
for FSL/Synth *and* ``registration=reg_wrap`` for ANTS' ``wire_transforms``).
The AI-branch applies (``func_2_sym_warp``/``ai_2_ref``) already passed
``warp=[inputnode, "<field>"]``, ``registration=None`` -- the composed-field
boundary path -- so those needed no change. The FSL snapshots below are
pinned explicitly and stay byte-identical. Session G (CP-G) added
``ants_backend`` as the golden ANTS-default snapshot, eye-reviewed alongside
the pre-existing node/edge construction test
(``test_func_map_ants_construction``), which keeps asserting the graph SHAPE
independently of the byte snapshot.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList, FreesurferStep
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

func_map_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.func_map_workflow", "func_map_workflow"
)

SUBDIR = "func_map"

# name -> (freesurfer_step, ai, config_input, wf_name)
SCENARIOS = {
    "no_freesurfer_no_ai": (FreesurferStep.DISABLED, False, DataInputList.ASL, "asl"),
    "no_freesurfer_ai": (FreesurferStep.DISABLED, True, DataInputList.ASL, "asl"),
    "synthseg_no_ai": (FreesurferStep.SYNTHSEG, False, DataInputList.ASL, "asl"),
    "reconall_no_ai": (FreesurferStep.RECONALL, False, DataInputList.ASL, "asl"),
    "reconall_ai": (FreesurferStep.RECONALL, True, DataInputList.ASL, "asl"),
    "pet_reconall_ai": (FreesurferStep.RECONALL, True, DataInputList.PET, "pet"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_func_map_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    freesurfer_step, ai, config_input, wf_name = SCENARIOS[scenario]
    section = subject_config[config_input]
    section["ai"] = "true" if ai else "false"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # func_map is not yet exercised under ANTS in this matrix; pin FSL so these
    # scenarios keep matching their existing golden snapshots.
    synth["engine"] = "FSL"

    wf = func_map_workflow(
        wf_name,
        dicom_dir=make_input_dir(),
        freesurfer_step=freesurfer_step,
        config=section,
        synth_config=synth,
    )

    config_echo = {
        "freesurfer_step": freesurfer_step.name,
        "ai": section["ai"],
        "cost_func": section["cost_func"],
        "config": config_input.name,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="func_map / %s" % scenario,
    )


def test_func_map_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True on the ASL baseline.

    func_map's registration to reference is linear-only, so test_run's only
    effect here is propagation through get_registration_node with no visible
    parameter change yet -- this locks in that the wiring doesn't break the
    graph as new linear-only speed knobs get added later.
    """
    section = subject_config[DataInputList.ASL]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    # func_map is not yet exercised under ANTS in this matrix; pin FSL so this
    # scenario keeps matching its existing golden snapshot.
    synth["engine"] = "FSL"

    wf = func_map_workflow(
        "asl",
        dicom_dir=make_input_dir(),
        freesurfer_step=FreesurferStep.DISABLED,
        config=section,
        synth_config=synth,
        test_run=True,
    )

    config_echo = {
        "freesurfer_step": FreesurferStep.DISABLED.name,
        "ai": section["ai"],
        "cost_func": section["cost_func"],
        "config": DataInputList.ASL.name,
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="func_map / test_run",
    )


def test_func_map_matrix_ants_backend(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """ANTS-default backend on the ASL asymmetry-index configuration -- the
    Phase 2 engine flip. See ``test_func_map_ants_construction`` below for the
    graph-shape assertions this golden snapshot locks in.
    """
    section = subject_config[DataInputList.ASL]
    section["ai"] = "true"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "ANTS"

    wf = func_map_workflow(
        "asl",
        dicom_dir=make_input_dir(),
        freesurfer_step=FreesurferStep.DISABLED,
        config=section,
        synth_config=synth,
    )

    config_echo = {
        "freesurfer_step": FreesurferStep.DISABLED.name,
        "ai": section["ai"],
        "cost_func": section["cost_func"],
        "registration_engine": "ANTS",
        "config": DataInputList.ASL.name,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="ants_backend",
        config=config_echo,
        title="func_map / ants_backend",
    )


# --------------------------------------------------------------------------- #
# ANTS-default construction (node/edge assertions, independent of the
# ``ants_backend`` byte snapshot above).
# --------------------------------------------------------------------------- #
def _iface(node):
    return type(node.interface).__name__


def _node_by_iface(wf, iface):
    return next(n for n in wf._graph.nodes() if _iface(n) == iface)


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _build_ants(subject_config, global_config, make_input_dir):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "ANTS"
    section = subject_config[DataInputList.ASL]
    section["ai"] = "true"
    return func_map_workflow(
        "asl",
        dicom_dir=make_input_dir(),
        freesurfer_step=FreesurferStep.DISABLED,
        config=section,
        synth_config=synth,
    )


def test_func_map_ants_construction(subject_config, global_config, make_input_dir):
    from nipype.interfaces.base import isdefined

    wf = _build_ants(subject_config, global_config, make_input_dir)
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("AntsRegistration") == 1
    assert ifaces.count("AntsApplyTransforms") == 3
    assert "FLIRT" not in ifaces and "ApplyXFM" not in ifaces
    assert "ApplyWarp" not in ifaces

    ants_reg = _node_by_iface(wf, "AntsRegistration")
    inputnode = next(n for n in wf._graph.nodes() if n.name == "inputnode")

    # smooth_2_ref: same-workflow reg_wrap reuse -> wire_transforms path
    # (direct transformlist + which_to_invert from the registration node, no
    # Merge boundary lifting).
    smooth_2_ref = next(
        n
        for n in wf._graph.nodes()
        if _iface(n) == "AntsApplyTransforms"
        and any(
            s is ants_reg and df == "transformlist" for s, sf, df in _incoming(wf, n)
        )
    )
    smooth_in = _incoming(wf, smooth_2_ref)
    assert (ants_reg, "fwd_transforms", "transformlist") in smooth_in
    assert (ants_reg, "fwd_which_to_invert", "which_to_invert") in smooth_in

    # func_2_sym_warp / ai_2_ref: composed-boundary single-field path (Merge(1)
    # from the inputnode field, no which_to_invert).
    boundary_applies = [
        n
        for n in wf._graph.nodes()
        if _iface(n) == "AntsApplyTransforms" and n is not smooth_2_ref
    ]
    assert len(boundary_applies) == 2

    seen_fields = set()
    for node in boundary_applies:
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
        seen_fields.add(src_field)
    assert seen_fields == {"ref_2_sym_warp", "ref_2_sym_invwarp"}


def test_func_map_fsl_construction_unchanged(
    subject_config, global_config, make_input_dir
):
    """The pin lift must not disturb the FSL graph: FLIRT + FNIRT-free linear
    applies (ApplyXFM), no ANTs."""
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = "FSL"
    section = subject_config[DataInputList.ASL]
    section["ai"] = "true"

    wf = func_map_workflow(
        "asl",
        dicom_dir=make_input_dir(),
        freesurfer_step=FreesurferStep.DISABLED,
        config=section,
        synth_config=synth,
    )
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("FLIRT") == 1
    assert ifaces.count("ApplyXFM") == 1
    assert ifaces.count("ApplyWarp") == 2
    assert "AntsRegistration" not in ifaces
    assert "AntsApplyTransforms" not in ifaces
