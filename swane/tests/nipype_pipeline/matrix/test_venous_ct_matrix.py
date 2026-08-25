"""Construction matrix for
:func:`swane.nipype_pipeline.workflows.venous_ct_workflow.venous_ct_workflow`.

CT-angiography veins pipeline. Phase 2 (CP-F) lifted this workflow's CT-specific
FSL pin (``# FLIRT performs better on CT``) and routed EVERY registration
through the backend-neutral abstraction (``get_registration_node`` /
``apply_registration_node``) -- there are no hand-built FLIRT/ApplyXFM nodes
left. It now takes a ``synth_config`` and follows the global engine (ANTs by
default); an explicit SynthMorph choice falls back to FSL (the known-worse
backend on CT), an ANTs config stays ANTs, an FSL config stays FSL.

Because the FSL registrations now come from the abstraction, their node names
changed, so the old byte snapshots (which described the previous hand-built
FLIRT/ApplyXFM graph) are obsolete and were removed. The engine-dimensioned
golden snapshots are (re)generated and eye-reviewed in Session G; here the graph
is covered by node/edge construction assertions for every engine outcome.
"""

from nipype import MapNode
from nipype.interfaces.base import isdefined

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

venous_ct_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.venous_ct_workflow", "venous_ct_workflow"
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


def _build(
    subject_config, global_config, make_input_dir, make_file, engine, test_run=False
):
    section = subject_config[DataInputList.VENOUS_CT]
    section["skull_threshold"] = "-1"
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["engine"] = engine
    return venous_ct_workflow(
        "venous_ct",
        venous_ct_dir=make_input_dir("noncontrast"),
        config=section,
        synth_config=synth,
        venous2_ct_dir=[make_input_dir("contrast_0"), make_input_dir("contrast_1")],
        slicer_path=make_file("Slicer.exe", "x"),
        test_run=test_run,
    )


def test_venous_ct_ants_construction(
    subject_config, global_config, make_input_dir, make_file
):
    wf = _build(subject_config, global_config, make_input_dir, make_file, "ANTS")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    # No FSL registration/apply nodes survive under ANTS.
    assert "FLIRT" not in ifaces
    assert "ApplyXFM" not in ifaces

    # Two AntsRegistration nodes: the basal->reference reference registration
    # (plain Node) and the contrast->basal MapNode.
    ants_regs = [n for n in wf._graph.nodes() if _iface(n) == "AntsRegistration"]
    assert len(ants_regs) == 2
    contrast_regs = [n for n in ants_regs if isinstance(n, MapNode)]
    basal_regs = [n for n in ants_regs if not isinstance(n, MapNode)]
    assert len(contrast_regs) == 1
    assert len(basal_regs) == 1

    # contrast->basal preserves the per-input iteration over the moving image.
    contrast_reg = contrast_regs[0]
    assert contrast_reg.iterfield == ["moving"]
    # its already-registered output feeds the subtraction MapNode.
    subtraction = next(n for n in wf._graph.nodes() if n.name == "veins_ct_subtraction")
    assert (contrast_reg, "warped_file", "in_file") in _incoming(wf, subtraction)

    # The final veins resample to reference is an AntsApplyTransforms that reuses
    # the in-workflow basal registration via the wire_transforms path (direct
    # transformlist + which_to_invert from the registration node, no Merge).
    basal_reg = basal_regs[0]
    veins_applies = [n for n in wf._graph.nodes() if _iface(n) == "AntsApplyTransforms"]
    assert len(veins_applies) == 1
    veins_apply = veins_applies[0]
    apply_in = _incoming(wf, veins_apply)
    assert (basal_reg, "fwd_transforms", "transformlist") in apply_in
    assert (basal_reg, "fwd_which_to_invert", "which_to_invert") in apply_in
    assert not any(_iface(s) == "Merge" for s, _, _ in apply_in)
    # The deterministic result filename is preserved on the abstraction node.
    assert veins_apply.inputs.out_file == "r-veins_ct_inskull.nii.gz"

    # basal output comes from the registration node's own warped output.
    outputnode = next(n for n in wf._graph.nodes() if n.name == "outputnode")
    assert (basal_reg, "warped_file", "basal") in _incoming(wf, outputnode)


def test_venous_ct_fsl_construction(
    subject_config, global_config, make_input_dir, make_file
):
    """Under FSL the abstraction builds two FLIRT (basal reg + the contrast
    map_moving MapNode over ``in_file``) and one ApplyXFM, no ANTs, no ApplyWarp
    (linear only)."""
    wf = _build(subject_config, global_config, make_input_dir, make_file, "FSL")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("FLIRT") == 2
    assert ifaces.count("ApplyXFM") == 1
    assert "AntsRegistration" not in ifaces
    assert "AntsApplyTransforms" not in ifaces

    contrast = next(
        n for n in wf._graph.nodes() if isinstance(n, MapNode) and _iface(n) == "FLIRT"
    )
    assert contrast.iterfield == ["in_file"]
    subtraction = next(n for n in wf._graph.nodes() if n.name == "veins_ct_subtraction")
    assert (contrast, "out_file", "in_file") in _incoming(wf, subtraction)

    apply_xfm = next(n for n in wf._graph.nodes() if _iface(n) == "ApplyXFM")
    assert apply_xfm.inputs.out_file == "r-veins_ct_inskull.nii.gz"


def test_venous_ct_synth_falls_back_to_fsl(
    subject_config, global_config, make_input_dir, make_file
):
    """SynthMorph underperforms on CT, so a SYNTH config builds the FSL graph
    (FLIRT), never a SynthMorph registration."""
    wf = _build(subject_config, global_config, make_input_dir, make_file, "SYNTH")
    ifaces = [_iface(n) for n in wf._graph.nodes()]
    assert ifaces.count("FLIRT") == 2
    assert "SynthMorphReg" not in ifaces
    assert "SynthMorphApply" not in ifaces
    assert "AntsRegistration" not in ifaces


def test_venous_ct_test_run_segment_override(
    subject_config, global_config, make_input_dir, make_file
):
    """test_run unconditionally drops the endocranium segmentation to the tool
    baseline (iteration 2, oversampling 1.0) even over an explicit user value."""
    section = subject_config[DataInputList.VENOUS_CT]
    section["segment_endocranium_iteration"] = "10"
    section["segment_endocranium_oversampling"] = "3.0"
    wf = _build(
        subject_config,
        global_config,
        make_input_dir,
        make_file,
        "FSL",
        test_run=True,
    )
    deskull = next(n for n in wf._graph.nodes() if n.name == "segment_endocranium")
    assert deskull.inputs.iterations == 2
    assert deskull.inputs.oversampling == 1.0

    # Without test_run the user's values flow through unchanged.
    section["segment_endocranium_iteration"] = "10"
    section["segment_endocranium_oversampling"] = "3.0"
    wf2 = _build(subject_config, global_config, make_input_dir, make_file, "FSL")
    deskull2 = next(n for n in wf2._graph.nodes() if n.name == "segment_endocranium")
    assert deskull2.inputs.iterations == 10
    assert deskull2.inputs.oversampling == 3.0
    assert isdefined(deskull2.inputs.iterations)
