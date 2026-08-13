"""Construction tests for
:func:`swane.nipype_pipeline.workflows.dti_preproc_workflow.dti_preproc_workflow`.

Covers the non-tractography DTI preprocessing graph and the eddy-correction
backend switch. The ``tractography=True`` branch needs the FSL ``$FSLDIR`` MNI
templates and is therefore left to the integration suite (see TODO_dicom.md).

``cuda`` is set explicitly on the section because it is a runtime-populated
preference not present in the bare workflow defaults.
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.dti_preproc_workflow import dti_preproc_workflow


def _names(workflow):
    return {node.name for node in workflow._graph.nodes()}


def _build(subject_config, global_config, dti_dir, *, old_eddy):
    section = subject_config[DataInputList.DTI]
    section["cuda"] = "false"
    section["tractography"] = "false"
    section["old_eddy_correct"] = "true" if old_eddy else "false"
    return dti_preproc_workflow(
        "dti",
        dti_dir=dti_dir,
        config=section,
        synth_config=global_config[GlobalPrefCategoryList.SYNTH],
    )


class TestDtiPreprocWorkflow:
    def test_core_nodes_present(self, subject_config, global_config, make_input_dir):
        """Conversion, b0 extraction, deskull, DTIFit and FA transform are wired."""
        wf = _build(subject_config, global_config, make_input_dir(), old_eddy=False)
        names = _names(wf)
        for expected in (
            "inputnode",
            "outputnode",
            "dti_conv",
            "dti_reOrient",
            "dti_nodif",
            "dti_deskull_bet",
            "dti_dtifit",
            "dti_eddy",
            "fa_2_ref_apply_xfm",
        ):
            assert expected in names

    def test_new_eddy_generates_eddy_files(
        self, subject_config, global_config, make_input_dir
    ):
        """The modern eddy path adds a GenEddyFiles (index/acqp) node."""
        wf = _build(subject_config, global_config, make_input_dir(), old_eddy=False)
        assert "dti_eddy_files" in _names(wf)

    def test_old_eddy_correct_skips_eddy_files(
        self, subject_config, global_config, make_input_dir
    ):
        """The legacy EddyCorrect path does not create the GenEddyFiles node."""
        wf = _build(subject_config, global_config, make_input_dir(), old_eddy=True)
        assert "dti_eddy_files" not in _names(wf)
