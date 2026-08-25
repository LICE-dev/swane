"""Construction matrix for
:func:`swane.nipype_pipeline.workflows.seeg_ct_workflow.seeg_ct_workflow`.

Post-implant CT electrode extraction. Phase 2 (CP-F) lifted this workflow's
CT-specific FSL pin (``# FLIRT performs better on CT``) and routed its
registration through the backend-neutral abstraction -- there is no hand-built
FLIRT node left. It now takes a ``synth_config`` and follows the global engine
(ANTs by default); an explicit SynthMorph choice falls back to FSL (the
known-worse backend on CT). The electrode weight map (0 on electrodes, 1
elsewhere) is passed once to the abstraction as ``moving_mask``, which wires it
as the ANTs metric ``moving_mask`` on ANTs and as FLIRT ``in_weight`` on FSL
(same map, correct polarity for both).

The FSL registration node name changed with the abstraction, so the old byte
snapshots are obsolete and were removed; the engine-dimensioned goldens are
(re)generated and eye-reviewed in Session G. Here the graph is covered by
node/edge construction assertions for every engine outcome.
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

seeg_ct_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.seeg_ct_workflow", "seeg_ct_workflow"
)


def _iface(node):
    return type(node.interface).__name__


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _build(subject_config, global_config, make_input_dir, engine):
    section = subject_config[DataInputList.SEEG_CT]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine
    return seeg_ct_workflow(
        "seeg_ct",
        seeg_ct_dir=make_input_dir(),
        config=section,
        synth_config=synth,
    )


def test_seeg_ct_ants_construction(subject_config, global_config, make_input_dir):
    wf = _build(subject_config, global_config, make_input_dir, "ANTS")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("AntsRegistration") == 1
    assert "FLIRT" not in ifaces

    ants_reg = next(n for n in wf._graph.nodes() if _iface(n) == "AntsRegistration")
    weight_map = next(n for n in wf._graph.nodes() if n.name == "electrodes_weight_bin")

    # The electrode weight map (0 on electrodes, 1 elsewhere) is the ANTs
    # moving_mask, i.e. the region the metric registers ON.
    reg_in = _incoming(wf, ants_reg)
    assert (weight_map, "out_file", "moving_mask") in reg_in

    # The registered seeg CT (warped_file) feeds both threshold segmentations.
    for thr_name in ("seeg_electrodes_thr_ref", "seeg_no_electrodes_thr_ref"):
        thr = next(n for n in wf._graph.nodes() if n.name == thr_name)
        assert (ants_reg, "warped_file", "in_file") in _incoming(wf, thr)


def test_seeg_ct_fsl_construction(subject_config, global_config, make_input_dir):
    """Under FSL the abstraction builds one FLIRT fed the electrode weight map
    through ``in_weight``, no ANTs; its ``out_file`` feeds the segmentations."""
    wf = _build(subject_config, global_config, make_input_dir, "FSL")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("FLIRT") == 1
    assert "AntsRegistration" not in ifaces

    flirt = next(n for n in wf._graph.nodes() if _iface(n) == "FLIRT")
    weight_map = next(n for n in wf._graph.nodes() if n.name == "electrodes_weight_bin")
    assert (weight_map, "out_file", "in_weight") in _incoming(wf, flirt)

    for thr_name in ("seeg_electrodes_thr_ref", "seeg_no_electrodes_thr_ref"):
        thr = next(n for n in wf._graph.nodes() if n.name == thr_name)
        assert (flirt, "out_file", "in_file") in _incoming(wf, thr)


def test_seeg_ct_synth_falls_back_to_fsl(subject_config, global_config, make_input_dir):
    """SynthMorph underperforms on CT, so a SYNTH config builds the FSL graph."""
    wf = _build(subject_config, global_config, make_input_dir, "SYNTH")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("FLIRT") == 1
    assert "SynthMorphReg" not in ifaces
    assert "AntsRegistration" not in ifaces
