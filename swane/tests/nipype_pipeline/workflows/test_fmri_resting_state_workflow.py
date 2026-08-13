"""Construction tests for
:func:`swane.nipype_pipeline.workflows.fMRI_resting_state_workflow.fMRI_resting_state_workflow`.

Only the AROMA-disabled path is exercised here: it builds the MELODIC ICA graph
directly on the preprocessed data. The AROMA-enabled path needs the FSL
``$FSLDIR`` MNI templates and is left to the integration suite (see
TODO_dicom.md).

``melodic_dim``/``melodic_thr`` are set explicitly on the section because they
are runtime-populated preferences absent from the bare workflow defaults.
"""

from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.fMRI_resting_state_workflow import (
    fMRI_resting_state_workflow,
)


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(subject_config, dicom_dir):
    section = subject_config[DataInputList["FMRI_0"]]
    section["aroma"] = "false"
    section["melodic_dim"] = "0"
    section["melodic_thr"] = "0.5"
    return fMRI_resting_state_workflow("fmri_0", dicom_dir=dicom_dir, config=section)


class TestFmriRestingStateWorkflow:
    def test_melodic_graph_without_aroma(self, subject_config, make_input_dir):
        """AROMA off wires MELODIC + output selection + z-stat registration."""
        wf = _build(subject_config, make_input_dir())
        names = _names(wf)
        assert "melodic" in names
        assert "melodic_output" in names
        assert "zstats_2_ref" in names

    def test_no_aroma_specific_nodes(self, subject_config, make_input_dir):
        """AROMA off must not create the AROMA preprocessing/classification nodes."""
        wf = _build(subject_config, make_input_dir())
        names = _names(wf)
        assert "preproc_melodic" not in names
        assert "aroma_classification" not in names
