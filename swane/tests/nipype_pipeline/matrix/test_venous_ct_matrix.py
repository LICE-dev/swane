"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.venous_ct_workflow.venous_ct_workflow`.

CT-angiography veins pipeline. The contrast scans are handled by MapNodes over a
list of directories and scalp removal uses the Slicer-backed SegmentEndocranium
node (its ``slicer_cmd`` only needs an existing file path — no Slicer run). The
matrix varies the number of contrast series and the automatic vs fixed skull
threshold. Snapshots under ``snapshots/venous_ct/``.
"""

import pytest

from swane.utils.DataInputList import DataInputList
from swane.tests.nipype_pipeline.matrix.conftest import import_workflow_or_skip

venous_ct_workflow = import_workflow_or_skip(
    "swane.nipype_pipeline.workflows.venous_ct_workflow", "venous_ct_workflow"
)

SUBDIR = "venous_ct"

# name -> (n_contrast_series, skull_threshold)
SCENARIOS = {
    "auto_threshold_two_contrast": (2, "-1"),
    "fixed_threshold_two_contrast": (2, "1500"),
    "single_contrast": (1, "-1"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_venous_ct_matrix(
    scenario, subject_config, make_input_dir, make_file, graph_snapshot
):
    n_contrast, skull_threshold = SCENARIOS[scenario]
    section = subject_config[DataInputList.VENOUS_CT]
    section["skull_threshold"] = skull_threshold

    contrast_dirs = [make_input_dir("contrast_%d" % i) for i in range(n_contrast)]
    wf = venous_ct_workflow(
        "venous_ct",
        venous_ct_dir=make_input_dir("noncontrast"),
        config=section,
        venous2_ct_dir=contrast_dirs,
        slicer_path=make_file("Slicer.exe", "x"),
    )

    config_echo = {
        "contrast_series": n_contrast,
        "skull_threshold": skull_threshold,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="venous_ct / %s" % scenario,
    )


def test_venous_ct_matrix_test_run(
    subject_config, make_input_dir, make_file, graph_snapshot
):
    """test_run=True, with the user explicitly away from the SWANe defaults.

    segment_endocranium_iteration/oversampling are set to values different
    from *both* the SWANe default (6 / 1.5) and the test_run target (2 /
    1.0), to prove in the golden file that test_run overrides them
    unconditionally (unlike most other test_run knobs, which only apply when
    the user left the default alone) -- see venous_ct_workflow.py.
    """
    section = subject_config[DataInputList.VENOUS_CT]
    section["skull_threshold"] = "-1"
    section["segment_endocranium_iteration"] = "10"
    section["segment_endocranium_oversampling"] = "3.0"

    wf = venous_ct_workflow(
        "venous_ct",
        venous_ct_dir=make_input_dir("noncontrast"),
        config=section,
        venous2_ct_dir=[make_input_dir("contrast_0")],
        slicer_path=make_file("Slicer.exe", "x"),
        test_run=True,
    )

    config_echo = {
        "contrast_series": 1,
        "skull_threshold": "-1",
        "segment_endocranium_iteration_user_value": "10",
        "segment_endocranium_oversampling_user_value": "3.0",
        "test_run": True,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name="test_run",
        config=config_echo,
        title="venous_ct / test_run",
    )
