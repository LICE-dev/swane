"""Settings matrix for
:func:`swane.nipype_pipeline.workflows.fMRI_task_workflow.fMRI_task_workflow`.

Construction of this workflow needs a real (or emulated, see
``swane/tests/conftest.py``) FSL >= 5.0.7: nipype's ``FILMGLS`` only exposes
the ``tcon_file``/``fcon_file`` inputs the builder wires from that version on
(see the former ``TODO_dicom.md`` §3). The ``block_design`` axis is the
graph-shape-relevant one: ``RARB`` adds a second contrast (and therefore a
second cluster-thresholding branch) on top of ``RARA``. Snapshots live under
``snapshots/fmri_task/``.
"""

import pytest

from swane.config.config_enums import BlockDesign
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_task_workflow import fMRI_task_workflow

SUBDIR = "fmri_task"

SCENARIOS = {
    "single_contrast_rara": BlockDesign.RARA,
    "two_contrasts_rarb": BlockDesign.RARB,
}


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fmri_task_matrix(scenario, subject_config, make_input_dir, graph_snapshot):
    block_design = SCENARIOS[scenario]
    section = subject_config[DataInputList.FMRI_0]
    section["block_design"] = block_design.name

    wf = fMRI_task_workflow(
        "fmri_0",
        dicom_dir=make_input_dir(),
        config=section,
    )

    config_echo = {
        "block_design": block_design.name,
        "task_a_name": section["task_a_name"],
        "task_b_name": section["task_b_name"],
        "task_duration": section["task_duration"],
        "rest_duration": section["rest_duration"],
    }
    graph_snapshot(
        wf,
        subdir=SUBDIR,
        name=scenario,
        config=config_echo,
        title="fmri_task / %s" % scenario,
    )
