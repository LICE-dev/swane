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
from swane.nipype_pipeline.workflows.venous_ct_workflow import venous_ct_workflow

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
