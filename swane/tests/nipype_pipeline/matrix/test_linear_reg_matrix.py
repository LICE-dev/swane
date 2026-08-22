"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.linear_reg_workflow.linear_reg_workflow`.

This single builder backs several inputs (3D FLAIR, post-contrast MDC, coronal
T2, 2D FLAIR). The graph is reshaped by the builder flags ``is_volumetric``,
``is_partial_coverage`` and ``bias_field_correction`` and by the SynthStrip/
SynthMorph backend, so each meaningful combination gets a golden snapshot under
``snapshots/linear_reg/``. MDC mirrors 3D FLAIR's flags exactly (see
``MainWorkflow.launch_mdc_analysis``) but reads its *own* preference section,
which has a different default in practice — kept as a separate scenario built
from ``DataInputList.MDC`` (not copy-pasted from FLAIR3D's) so that default is
actually exercised rather than assumed identical.
"""

import pytest

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

linear_reg_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.linear_reg_workflow", "linear_reg_workflow"
)

SUBDIR = "linear_reg"

# name -> dict(builder flags + backend/config), mirroring how MainWorkflow calls
# this factory for each modality.
SCENARIOS = {
    # 3D FLAIR: volumetric, bias-field corrected, own BET config.
    "flair3d_bias": dict(
        volumetric=True,
        partial=False,
        bias=True,
        synth=False,
        config_input=DataInputList.FLAIR3D,
        wf_name="flair3d",
    ),
    "flair3d_no_bias": dict(
        volumetric=True,
        partial=False,
        bias=False,
        synth=False,
        config_input=DataInputList.FLAIR3D,
        wf_name="flair3d",
    ),
    # Post-contrast 3D T1w (MDC): same flags as 3D FLAIR, own preference section.
    "mdc_bias": dict(
        volumetric=True,
        partial=False,
        bias=True,
        synth=False,
        config_input=DataInputList.MDC,
        wf_name="mdc",
    ),
    # Coronal T2: volumetric + partial coverage (reuses the reference brain mask).
    "t2cor_partial_coverage": dict(
        volumetric=True,
        partial=True,
        bias=False,
        synth=False,
        config_input=None,
        wf_name="t2_cor",
    ),
    # 2D FLAIR: non-volumetric, no per-input config.
    "flair2d_non_volumetric": dict(
        volumetric=False,
        partial=False,
        bias=False,
        synth=False,
        config_input=None,
        wf_name="flair2d",
    ),
    # SynthStrip + SynthMorph backend on the 3D FLAIR configuration.
    "flair3d_synth_backend": dict(
        volumetric=True,
        partial=False,
        bias=True,
        synth=True,
        config_input=DataInputList.FLAIR3D,
        wf_name="flair3d",
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

    config = (
        subject_config[params["config_input"]]
        if params["config_input"] is not None
        else None
    )

    wf = linear_reg_workflow(
        params["wf_name"],
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
        "config": params["config_input"].name if params["config_input"] else "None",
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="linear_reg / %s" % scenario,
    )


def test_linear_reg_matrix_test_run(
    subject_config, global_config, make_input_dir, graph_snapshot
):
    """test_run=True on the 3D FLAIR / bias-corrected configuration.

    Exercises both the shared get_registration_node speed knobs and the N4
    max_iterations cap (bias_field_correction=True), which prerelease's
    default test_run=True actually builds for FLAIR3D/MDC.
    """
    synth = global_config[GlobalPrefCategoryList.SYNTH]
    config = subject_config[DataInputList.FLAIR3D]

    wf = linear_reg_workflow(
        "flair3d",
        dicom_dir=make_input_dir(),
        config=config,
        synth_config=synth,
        is_volumetric=True,
        is_partial_coverage=False,
        bias_field_correction=True,
        test_run=True,
    )

    config_echo = {
        "is_volumetric": True,
        "is_partial_coverage": False,
        "bias_field_correction": True,
        "synth_strip": synth["strip"],
        "synth_morph": synth["morph"],
        "config": DataInputList.FLAIR3D.name,
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="linear_reg / test_run",
    )
