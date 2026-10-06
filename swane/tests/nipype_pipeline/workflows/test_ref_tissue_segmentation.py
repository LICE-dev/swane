"""Graph tests for the shared reference tissue segmentation of
:func:`swane.nipype_pipeline.workflows.ref_workflow.ref_workflow`.

The segmentation runs once in the reference workflow (``ref_segmentation``)
and its [CSF, GM, WM] maps are consumed by FLAT1, dipy tractography and the
NILEARN resting state. Only the graph is built; no node is executed.
"""

import pytest
from nipype.interfaces.base import isdefined

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow

OUTPUT_FIELDS = [
    "reference",
    "reference_brain",
    "ref_mask",
    "uncorrected_reference",
    "uncorrected_reference_brain",
]


def _incoming(wf, dst_node):
    conns = []
    for src, dst, data in wf._graph.edges(data=True):
        if dst is dst_node:
            for src_field, dst_field in data.get("connect", []):
                conns.append((src, src_field, dst_field))
    return conns


def _sources(wf, dst_node):
    """dst_field -> (src node name, src field)."""
    return {df: (src.name, sf) for src, sf, df in _incoming(wf, dst_node)}


def _iface(node):
    return type(node.interface).__name__


def _build(
    subject_config,
    global_config,
    make_input_dir,
    segmentation="ANTS",
    max_cpu=4,
    test_run=False,
    **kwargs
):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["segmentation_engine"] = segmentation
    return ref_workflow(
        "ref",
        dicom_dir=make_input_dir(),
        config=subject_config[DataInputList.T13D],
        synth_config=synth,
        max_cpu=max_cpu,
        test_run=test_run,
        **kwargs
    )


@pytest.mark.parametrize("segmentation", ["ANTS", "FSL"])
def test_no_segmentation_by_default(
    subject_config, global_config, make_input_dir, segmentation
):
    wf = _build(subject_config, global_config, make_input_dir, segmentation)
    assert wf.get_node("ref_segmentation") is None
    ifaces = {_iface(n) for n in wf._graph.nodes()}
    assert not ifaces & {"AntsAtropos", "FAST"}

    outputnode = wf.get_node("outputnode")
    sources = _sources(wf, outputnode)
    # existing outputs keep their sources; the tissue fields stay unconnected
    deskull = next(
        n.name for n in wf._graph.nodes() if n.name.startswith("ref_deskull_biased")
    )
    assert sources == {
        "reference": ("ref_bias_correction", "out_file"),
        "reference_brain": ("ref_corrected_deskull", "out_file"),
        "ref_mask": (deskull, "mask_file"),
        "uncorrected_reference": ("ref_reScale", "out_file"),
        "uncorrected_reference_brain": (deskull, "out_file"),
    }


def test_flag_false_matches_default(subject_config, global_config, make_input_dir):
    default = _build(subject_config, global_config, make_input_dir)
    explicit = _build(
        subject_config, global_config, make_input_dir, tissue_segmentation=False
    )
    assert {n.name for n in default._graph.nodes()} == {
        n.name for n in explicit._graph.nodes()
    }


def test_ants_atropos_on_corrected_brain(subject_config, global_config, make_input_dir):
    wf = _build(
        subject_config, global_config, make_input_dir, "ANTS", tissue_segmentation=True
    )
    seg = wf.get_node("ref_segmentation")
    assert _iface(seg) == "AntsAtropos"
    # Atropos has no internal bias correction: N4-corrected brain
    assert _sources(wf, seg) == {"in_file": ("ref_corrected_deskull", "out_file")}
    # default EM iterations when not a test run
    assert seg.inputs.iterations == 10

    sources = _sources(wf, wf.get_node("outputnode"))
    assert sources["tissue_pve"] == ("ref_segmentation", "partial_volume_files")
    assert sources["tissue_restored"] == ("ref_corrected_deskull", "out_file")
    assert sources["reference_brain"] == ("ref_corrected_deskull", "out_file")


def test_fsl_fast_on_uncorrected_brain(subject_config, global_config, make_input_dir):
    wf = _build(
        subject_config, global_config, make_input_dir, "FSL", tissue_segmentation=True
    )
    seg = wf.get_node("ref_segmentation")
    assert _iface(seg) == "FAST"
    deskull = next(
        n.name for n in wf._graph.nodes() if n.name.startswith("ref_deskull_biased")
    )
    # FAST runs its own bias correction: uncorrected brain
    assert _sources(wf, seg) == {"in_files": (deskull, "out_file")}
    assert seg.inputs.img_type == 1
    assert seg.inputs.number_classes == 3
    assert seg.inputs.hyper == 0.1
    assert seg.inputs.bias_lowpass == 40
    assert seg.inputs.output_biascorrected is True
    assert seg.inputs.bias_iters == 4
    assert type(seg.ram_estimator).__name__ == "FastRamEstimator"

    sources = _sources(wf, wf.get_node("outputnode"))
    assert sources["tissue_pve"] == ("ref_segmentation", "partial_volume_files")
    assert sources["tissue_restored"] == ("ref_segmentation", "restored_image")


def test_test_run_cuts_segmentation_iterations(
    subject_config, global_config, make_input_dir
):
    ants = _build(
        subject_config,
        global_config,
        make_input_dir,
        "ANTS",
        test_run=True,
        tissue_segmentation=True,
    ).get_node("ref_segmentation")
    assert ants.inputs.iterations == 3

    fast = _build(
        subject_config,
        global_config,
        make_input_dir,
        "FSL",
        test_run=True,
        tissue_segmentation=True,
    ).get_node("ref_segmentation")
    assert (fast.inputs.bias_iters, fast.inputs.segment_iters) == (1, 5)
    assert fast.inputs.iters_afterbias == 1


def test_atropos_num_threads_budgeted(subject_config, global_config, make_input_dir):
    """Atropos (ITK) gets a real num_threads/n_procs reservation from the CPU
    budget, like the antspynet deskull node -- so it cannot oversubscribe."""
    global_config[GlobalPrefCategoryList.SYNTH]["limit_cores"] = "false"
    seg = _build(
        subject_config,
        global_config,
        make_input_dir,
        "ANTS",
        max_cpu=4,
        tissue_segmentation=True,
    ).get_node("ref_segmentation")
    assert seg.inputs.num_threads == 4
    assert seg.n_procs == 4


def test_atropos_unbudgeted_when_max_cpu_zero(
    subject_config, global_config, make_input_dir
):
    seg = _build(
        subject_config,
        global_config,
        make_input_dir,
        "ANTS",
        max_cpu=0,
        tissue_segmentation=True,
    ).get_node("ref_segmentation")
    assert not isdefined(seg.inputs.num_threads)
