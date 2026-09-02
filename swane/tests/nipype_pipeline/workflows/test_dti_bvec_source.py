"""The FSL DTI branch must consume eddy's rotated b-vectors, not the raw ones.

Rotating the volumes without reorienting the gradients biases FA/MD and
tractography (Leemans & Jones 2009). FSL ``eddy`` emits ``out_rotated_bvecs``
for this purpose; ``eddy_correct`` does not, so the legacy branch keeps the
unrotated vectors because nothing better exists there.
"""

import pytest

from swane.config.config_enums import CoreLimit, DeskullModality


def _bvec_sources(workflow, consumer_name):
    """Return {(source node name, source field)} feeding ``consumer_name.bvecs``."""
    sources = set()
    for src, dst, data in workflow._graph.edges(data=True):
        if dst.name != consumer_name:
            continue
        for out_field, in_field in data.get("connect", []):
            if in_field == "bvecs":
                sources.add((src.name, out_field))
    return sources


def _build(subject_config, global_config, make_input_dir, fast):
    from swane.nipype_pipeline.workflows.dti_preproc_workflow import (
        dti_preproc_workflow,
    )
    from swane.utils.DataInputList import DataInputList

    subject_config[DataInputList.DTI]["old_eddy_correct"] = "true" if fast else "false"
    subject_config[DataInputList.DTI]["tractography"] = "true"
    subject_config[DataInputList.DTI]["cuda"] = "false"
    return dti_preproc_workflow(
        name="dti_preproc",
        dti_dir=str(make_input_dir("dti")),
        config=subject_config[DataInputList.DTI],
        synth_config=global_config[
            __import__(
                "swane.config.config_enums", fromlist=["GlobalPrefCategoryList"]
            ).GlobalPrefCategoryList.SYNTH
        ],
        deskull_modality=DeskullModality.NODIF,
        max_cpu=4,
        multicore_node_limit=CoreLimit.HARD_CAP,
    )


@pytest.mark.parametrize("consumer", ["dti_dtifit", "dti_bedpostx"])
def test_full_eddy_feeds_rotated_bvecs(
    consumer, subject_config, global_config, make_input_dir
):
    workflow = _build(subject_config, global_config, make_input_dir, fast=False)
    assert _bvec_sources(workflow, consumer) == {("dti_eddy", "out_rotated_bvecs")}


@pytest.mark.parametrize("consumer", ["dti_dtifit", "dti_bedpostx"])
def test_fast_path_keeps_conversion_bvecs(
    consumer, subject_config, global_config, make_input_dir
):
    """``eddy_correct`` emits no rotated bvecs, so the raw ones are correct here."""
    workflow = _build(subject_config, global_config, make_input_dir, fast=True)
    assert _bvec_sources(workflow, consumer) == {("dti_conv", "bvecs")}
