"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.seeg_ct_workflow.seeg_ct_workflow`.

Post-implant CT electrode extraction. The graph topology is fixed; the tunable
preferences (electrode threshold, brain-mask erosion kernel) flow into node
inputs, so the matrix records a default and a tuned scenario under
``snapshots/seeg_ct/`` to make those values reviewable by hand.
"""

import pytest

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.seeg_ct_workflow import seeg_ct_workflow

SUBDIR = "seeg_ct"

# name -> (electrode_threshold, erode_kernel_size)
SCENARIOS = {
    "default": ("2000", "5"),
    "tuned_threshold_kernel": ("2500", "8"),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_seeg_ct_matrix(scenario, subject_config, make_input_dir, graph_snapshot):
    electrode_threshold, erode_kernel = SCENARIOS[scenario]
    section = subject_config[DataInputList.SEEG_CT]
    section["electrode_threshold"] = electrode_threshold
    section["erode_kernel_size"] = erode_kernel

    wf = seeg_ct_workflow(
        "seeg_ct",
        seeg_ct_dir=make_input_dir(),
        config=section,
    )

    config_echo = {
        "electrode_threshold": electrode_threshold,
        "erode_kernel_size": erode_kernel,
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="seeg_ct / %s" % scenario,
    )
