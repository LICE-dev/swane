"""Per-site antspynet deskull modality wiring (Task 10).

Each of the four deskull-using workflow builders gains a ``deskull_modality``
parameter that it forwards to ``get_deskull_node``. With the default
``deskull_engine`` (ANTSPYNET), the built ``<name>_antspynet`` node must carry
the antspynet modality key of the modality passed by the builder's caller
(``MainWorkflow`` sets the correct value per site).

These are graph-construction asserts: no external tool runs, no snapshot.
"""

import pytest

from swane.config.config_enums import (
    GlobalPrefCategoryList,
    CoreLimit,
    DeskullEngine,
    DeskullModality,
)
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

linear_reg_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.linear_reg_workflow", "linear_reg_workflow"
)
ref_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.ref_workflow", "ref_workflow"
)
dti_preproc_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.dti_preproc_workflow", "dti_preproc_workflow"
)
venous_mr_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.venous_mr_workflow", "venous_mr_workflow"
)

MAX_CPU = 4


def _antspynet_synth(global_config):
    """Return the SYNTH section pinned to the ANTSPYNET deskull engine."""
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["deskull_engine"] = DeskullEngine.ANTSPYNET.name
    return synth


def _modality_of(wf, node_name):
    return wf.get_node(node_name).inputs.modality


def test_linear_reg_forwards_flair_modality(
    subject_config, global_config, make_input_dir
):
    synth = _antspynet_synth(global_config)
    wf = linear_reg_workflow(
        "flair",
        dicom_dir=make_input_dir(),
        config=subject_config[DataInputList.FLAIR3D],
        synth_config=synth,
        is_volumetric=True,
        is_partial_coverage=False,
        bias_field_correction=True,
        deskull_modality=DeskullModality.FLAIR,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _modality_of(wf, "flair_deskull_antspynet") == DeskullModality.FLAIR.value
    assert DeskullModality.FLAIR.value == "flair"


def test_linear_reg_defaults_to_t1_modality(
    subject_config, global_config, make_input_dir
):
    synth = _antspynet_synth(global_config)
    wf = linear_reg_workflow(
        "mdc",
        dicom_dir=make_input_dir(),
        config=subject_config[DataInputList.MDC],
        synth_config=synth,
        is_volumetric=True,
        is_partial_coverage=False,
        bias_field_correction=True,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _modality_of(wf, "mdc_deskull_antspynet") == DeskullModality.T1.value


def test_ref_forwards_t1_modality(subject_config, global_config, make_input_dir):
    synth = _antspynet_synth(global_config)
    wf = ref_workflow(
        "ref",
        dicom_dir=make_input_dir(),
        config=subject_config[DataInputList.T13D],
        synth_config=synth,
        deskull_modality=DeskullModality.T1,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _modality_of(wf, "ref_deskull_biased_antspynet") == DeskullModality.T1.value


def test_dti_forwards_nodif_modality(subject_config, global_config, make_input_dir):
    synth = _antspynet_synth(global_config)
    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["old_eddy_correct"] = "false"
    section["tractography"] = "false"
    wf = dti_preproc_workflow(
        "dti",
        dti_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        deskull_modality=DeskullModality.NODIF,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _modality_of(wf, "dti_deskull_antspynet") == DeskullModality.NODIF.value


def test_venous_mr_forwards_venous_modality(
    subject_config, global_config, make_input_dir
):
    synth = _antspynet_synth(global_config)
    wf = venous_mr_workflow(
        "venous_mr",
        venous_mr_dir=make_input_dir(),
        config=subject_config[DataInputList.VENOUS_MR],
        synth_config=synth,
        deskull_modality=DeskullModality.VENOUS,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _modality_of(wf, "vein_mr_deskull_antspynet") == DeskullModality.VENOUS.value


def _threshold_of(wf, node_name):
    return wf.get_node(node_name).inputs.threshold


def test_ref_forwards_antspynet_threshold(
    subject_config, global_config, make_input_dir
):
    synth = _antspynet_synth(global_config)
    section = subject_config[DataInputList.T13D]
    section["antspynet_thr"] = "0.6"
    wf = ref_workflow(
        "ref",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        deskull_modality=DeskullModality.T1,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _threshold_of(wf, "ref_deskull_biased_antspynet") == 0.6


def test_linear_reg_forwards_antspynet_threshold(
    subject_config, global_config, make_input_dir
):
    synth = _antspynet_synth(global_config)
    section = subject_config[DataInputList.FLAIR3D]
    section["antspynet_thr"] = "0.6"
    wf = linear_reg_workflow(
        "flair",
        dicom_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        is_volumetric=True,
        is_partial_coverage=False,
        bias_field_correction=True,
        deskull_modality=DeskullModality.FLAIR,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _threshold_of(wf, "flair_deskull_antspynet") == 0.6


def test_venous_mr_forwards_antspynet_threshold(
    subject_config, global_config, make_input_dir
):
    synth = _antspynet_synth(global_config)
    section = subject_config[DataInputList.VENOUS_MR]
    section["antspynet_thr"] = "0.6"
    wf = venous_mr_workflow(
        "venous_mr",
        venous_mr_dir=make_input_dir(),
        config=section,
        synth_config=synth,
        deskull_modality=DeskullModality.VENOUS,
        max_cpu=MAX_CPU,
        multicore_node_limit=CoreLimit.SOFT_CAP,
    )
    assert _threshold_of(wf, "vein_mr_deskull_antspynet") == 0.6
