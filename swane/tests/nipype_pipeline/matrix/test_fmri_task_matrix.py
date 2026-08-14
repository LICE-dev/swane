"""Known-bug guard for
:func:`swane.nipype_pipeline.workflows.fMRI_task_workflow.fMRI_task_workflow`.

The task-fMRI builder currently fails to construct with the pinned nipype
(1.10): the FILMGLS interface no longer accepts the ``tcon_file`` input the
builder wires (see ``TODO_dicom.md`` §3). Until the builder is realigned, the
graph cannot be assembled — not even for a snapshot — so this is tracked as a
strict ``xfail``. When the builder is fixed the test will XPASS, flagging that a
real ``snapshots/fmri_task/`` matrix should be added here.
"""

import pytest

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_task_workflow import fMRI_task_workflow


@pytest.mark.xfail(
    reason="FILMGLS no longer accepts tcon_file in nipype 1.10 (TODO_dicom.md §3)",
    strict=True,
)
def test_fmri_task_construction_currently_broken(subject_config, make_input_dir):
    section = subject_config[DataInputList["FMRI_0"]]
    fMRI_task_workflow("fmri_0", dicom_dir=make_input_dir(), config=section)
