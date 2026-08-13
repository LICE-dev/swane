"""Construction tests for
:func:`swane.nipype_pipeline.workflows.tractography_workflow.tractography_workflow`.

A full tract graph needs the FSL XTRACT protocol data directory, so only the
guard behaviour is testable without FSL: an unknown tract name (or a missing
protocol directory) makes the builder return ``None``. Building a real tract is
covered in the integration suite (see TODO_dicom.md).
"""

from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from swane.nipype_pipeline.workflows.tractography_workflow import tractography_workflow


class TestTractographyWorkflowGuards:
    def test_unknown_tract_returns_none(self, subject_config, global_config):
        """A tract name absent from the protocol list yields ``None``."""
        result = tractography_workflow(
            "definitely_not_a_tract",
            config=subject_config[DataInputList.DTI],
            synth_config=global_config[GlobalPrefCategoryList.SYNTH],
        )
        assert result is None
