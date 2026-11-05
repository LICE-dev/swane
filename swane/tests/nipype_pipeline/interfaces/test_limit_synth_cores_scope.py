"""Scope of the "Limit Synth tools to N CPU cores" preference (``limit_cores``).

The preference caps FreeSurfer Synth tools (SynthStrip, SynthMorph, SynthSeg)
at ``ResourceManager.SYNTH_CORE_LIMIT``. The ANTs-based nodes (registration,
antspynet brain extraction, Atropos) are not Synth tools: they always take the
subject CPU budget, whatever the preference says. Only graphs are built; no
node runs, so the budget need not exist on this host.
"""

import pytest
from nipype import Node
from nipype.interfaces.utility import IdentityInterface

from swane.config.config_enums import (
    DeskullEngine,
    DeskullModality,
    GlobalPrefCategoryList,
    RegistrationEngine,
)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.interfaces.utils import (
    get_deskull_node,
    get_registration_node,
)
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow
from swane.utils.DataInputList import DataInputList
from swane.utils.ResourceManager import ResourceManager

# A subject budget well above the Synth cap, as in the review scenario.
_BUDGET = 16


def _registration_node(engine, limit_synth_cores, **kwargs):
    wf = CustomWorkflow(name="wf")
    src = Node(IdentityInterface(fields=["moving", "reference"]), name="src")
    wrap = get_registration_node(
        name="reg",
        engine=engine,
        workflow=wf,
        moving=[src, "moving"],
        reference=[src, "reference"],
        max_cpu=_BUDGET,
        limit_synth_cores=limit_synth_cores,
        **kwargs,
    )
    return wrap.out_registered_node


@pytest.mark.parametrize("limit_synth_cores", [False, True])
@pytest.mark.parametrize("non_linear", [False, True])
def test_ants_registration_ignores_the_synth_limit(limit_synth_cores, non_linear):
    node = _registration_node(
        RegistrationEngine.ANTS, limit_synth_cores, non_linear=non_linear
    )
    assert node.inputs.num_threads == _BUDGET
    assert node.n_procs == _BUDGET


def test_synthmorph_registration_keeps_the_synth_limit():
    node = _registration_node(RegistrationEngine.SYNTH, True)
    assert node.inputs.num_threads == ResourceManager.SYNTH_CORE_LIMIT


@pytest.mark.parametrize("limit_synth_cores", [False, True])
def test_antspynet_deskull_ignores_the_synth_limit(limit_synth_cores):
    node = get_deskull_node(
        name="d",
        deskull_engine=DeskullEngine.ANTSPYNET,
        deskull_modality=DeskullModality.T1,
        mask=True,
        max_cpu=_BUDGET,
        limit_synth_cores=limit_synth_cores,
    )
    assert node.inputs.num_threads == _BUDGET
    assert node.n_procs == _BUDGET


def test_synthstrip_deskull_keeps_the_synth_limit():
    node = get_deskull_node(
        name="d",
        deskull_engine=DeskullEngine.SYNTHSTRIP,
        deskull_modality=DeskullModality.T1,
        max_cpu=_BUDGET,
        limit_synth_cores=True,
    )
    assert node.inputs.num_threads == ResourceManager.SYNTH_CORE_LIMIT


@pytest.mark.parametrize("limit_cores", ["false", "true"])
def test_atropos_ignores_the_synth_limit(
    subject_config, global_config, make_input_dir, limit_cores
):
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["segmentation_engine"] = "ANTS"
    synth["limit_cores"] = limit_cores
    seg = ref_workflow(
        "ref",
        dicom_dir=make_input_dir(),
        config=subject_config[DataInputList.T13D],
        synth_config=synth,
        max_cpu=_BUDGET,
        tissue_segmentation=True,
    ).get_node("ref_segmentation")
    assert seg.inputs.num_threads == _BUDGET
    assert seg.n_procs == _BUDGET
