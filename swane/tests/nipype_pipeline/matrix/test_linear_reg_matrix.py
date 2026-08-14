"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.linear_reg_workflow.linear_reg_workflow`.

This single builder backs several inputs (3D FLAIR, post-contrast MDC, coronal
T2, 2D FLAIR). The graph is reshaped by the builder flags ``is_volumetric``,
``is_partial_coverage`` and ``bias_field_correction`` and by the SynthStrip/
SynthMorph backend, so each meaningful combination gets a golden snapshot under
``snapshots/linear_reg/``.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.linear_reg_workflow import linear_reg_workflow

SUBDIR = "linear_reg"

# name -> dict(builder flags + backend/config), mirroring how MainWorkflow calls
# this factory for each modality.
SCENARIOS = {
    # 3D FLAIR: volumetric, bias-field corrected, own BET config.
    "flair3d_bias": dict(
        volumetric=True, partial=False, bias=True, synth=False, use_config=True
    ),
    "flair3d_no_bias": dict(
        volumetric=True, partial=False, bias=False, synth=False, use_config=True
    ),
    # Coronal T2: volumetric + partial coverage (reuses the reference brain mask).
    "t2cor_partial_coverage": dict(
        volumetric=True, partial=True, bias=False, synth=False, use_config=False
    ),
    # 2D FLAIR: non-volumetric, no per-input config.
    "flair2d_non_volumetric": dict(
        volumetric=False, partial=False, bias=False, synth=False, use_config=False
    ),
    # SynthStrip + SynthMorph backend on the 3D FLAIR configuration.
    "flair3d_synth_backend": dict(
        volumetric=True, partial=False, bias=True, synth=True, use_config=True
    ),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_linear_reg_matrix(
    scenario, subject_config, global_config, make_input_dir, graph_snapshot
):
    params = SCENARIOS[scenario]
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    synth["strip"] = "true" if params["synth"] else "false"
    synth["morph"] = "true" if params["synth"] else "false"

    config = subject_config[DataInputList.FLAIR3D] if params["use_config"] else None

    wf = linear_reg_workflow(
        "flair",
        dicom_dir=make_input_dir(),
        config=config,
        synth_config=synth,
        is_volumetric=params["volumetric"],
        is_partial_coverage=params["partial"],
        bias_field_correction=params["bias"],
    )

    config_echo = {
        "is_volumetric": params["volumetric"],
        "is_partial_coverage": params["partial"],
        "bias_field_correction": params["bias"],
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
        "config": "FLAIR3D" if params["use_config"] else "None",
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="linear_reg / %s" % scenario,
    )
