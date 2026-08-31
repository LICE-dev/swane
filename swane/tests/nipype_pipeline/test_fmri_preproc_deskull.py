"""fMRI_preproc mean-func brain extraction routed through the deskull wrapper
(Task 11).

The mean-functional mask node used to be a hardcoded FSL ``BET``. It now goes
through ``get_deskull_node`` with ``resolve_deskull_engine(..,
allow_synthstrip=False)`` and ``DeskullModality.BOLD``: EPI must avoid the
FreeSurfer Synth tools (mirroring the SynthMorph exclusion), so a configured
SYNTHSTRIP engine folds to the default ANTSPYNET, while ANTSPYNET and BET are
honoured.

These are graph-construction asserts: no external tool runs, no snapshot.
"""

import pytest

from swane.config.config_enums import (
    SliceTiming,
    GlobalPrefCategoryList,
    DeskullEngine,
    DeskullModality,
)
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
from nipype.interfaces.fsl import BET
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

fMRI_preproc_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.fMRI_preproc_workflow", "fMRI_preproc_workflow"
)


def _build(global_config, make_input_dir, deskull_engine):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["deskull_engine"] = deskull_engine.name
    return fMRI_preproc_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        TR=2.0,
        slice_timing=SliceTiming.UNKNOWN,
        n_vols=100,
        del_start_vols=0,
        del_end_vols=0,
        hpcutoff=30,
        synth_config=synth,
    )


def _meanfuncmask_node(wf):
    return next(n for n in wf._graph.nodes() if "meanfuncmask" in n.name)


def test_meanfuncmask_default_is_antspynet_bold(global_config, make_input_dir):
    wf = _build(global_config, make_input_dir, DeskullEngine.ANTSPYNET)
    node = _meanfuncmask_node(wf)
    assert node.name == "fmri_0_meanfuncmask_antspynet"
    assert isinstance(node.interface, AntsPyNetBrainExtraction)
    assert node.inputs.modality == DeskullModality.BOLD.value == "bold"


def test_meanfuncmask_synthstrip_excluded_folds_to_antspynet(
    global_config, make_input_dir
):
    # EPI must avoid the Synth tools: a configured SYNTHSTRIP engine must NOT
    # produce a SynthStrip node here; it folds to the default ANTSPYNET.
    wf = _build(global_config, make_input_dir, DeskullEngine.SYNTHSTRIP)
    node = _meanfuncmask_node(wf)
    assert node.name.endswith("_antspynet")
    assert isinstance(node.interface, AntsPyNetBrainExtraction)
    assert node.inputs.modality == "bold"
    node_types = {type(n.interface).__name__ for n in wf._graph.nodes()}
    assert "SynthStrip" not in node_types


def test_meanfuncmask_bet_engine_honoured(global_config, make_input_dir):
    wf = _build(global_config, make_input_dir, DeskullEngine.BET)
    node = _meanfuncmask_node(wf)
    assert node.name == "fmri_0_meanfuncmask_bet"
    assert isinstance(node.interface, BET)
