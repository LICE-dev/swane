"""Unit tests for :mod:`swane.nipype_pipeline.engine.WorkflowReport`.

Pure-Python logic: no external neuroimaging tool is required.

:class:`WorkflowReport` is the message object the workflow engine puts on the
inter-process queue to signal node/workflow state changes to the UI. These
tests pin down its two non-trivial behaviours: coercion of unknown signal
types to ``INVALID_SIGNAL`` and the parsing of a nipype ``fullname`` into a
separate workflow name and node name.
"""

from swane.nipype_pipeline.engine.WorkflowReport import (
    WorkflowReport,
    WorkflowSignals,
)


class TestWorkflowSignals:
    """Sanity checks on the :class:`WorkflowSignals` enumeration."""

    def test_members_are_unique(self):
        """Every signal must map to a distinct ``auto()`` value.

        Duplicated values would make two logically different signals compare
        equal and silently collapse in ``if report.signal_type == ...`` checks.
        """
        values = [member.value for member in WorkflowSignals]
        assert len(values) == len(set(values))

    def test_expected_members_exist(self):
        """The signals relied upon across the engine/UI must all be present."""
        for name in (
            "NODE_STARTED",
            "NODE_COMPLETED",
            "NODE_ERROR",
            "WORKFLOW_INSUFFICIENT_RESOURCES",
            "WORKFLOW_STOP",
            "INVALID_SIGNAL",
        ):
            assert hasattr(WorkflowSignals, name)


class TestWorkflowReport:
    """Behaviour of the :class:`WorkflowReport` constructor."""

    def test_default_signal_type_is_node_started(self):
        """With no arguments the report defaults to a ``NODE_STARTED`` signal."""
        report = WorkflowReport()
        assert report.signal_type == WorkflowSignals.NODE_STARTED

    def test_invalid_signal_type_is_coerced(self):
        """A non-:class:`WorkflowSignals` value is coerced to ``INVALID_SIGNAL``.

        Guards the queue consumer from ever receiving an arbitrary object as a
        signal type.
        """
        report = WorkflowReport(signal_type="not-a-signal")
        assert report.signal_type == WorkflowSignals.INVALID_SIGNAL

    def test_none_signal_type_is_coerced(self):
        """``None`` is not a valid signal and is coerced to ``INVALID_SIGNAL``."""
        report = WorkflowReport(signal_type=None)
        assert report.signal_type == WorkflowSignals.INVALID_SIGNAL

    def test_valid_signal_type_is_preserved(self):
        """A genuine :class:`WorkflowSignals` member is stored unchanged."""
        report = WorkflowReport(signal_type=WorkflowSignals.NODE_ERROR)
        assert report.signal_type == WorkflowSignals.NODE_ERROR

    def test_no_long_name_leaves_names_none(self):
        """Without a ``long_name`` both parsed name fields stay ``None``."""
        report = WorkflowReport(signal_type=WorkflowSignals.NODE_COMPLETED)
        assert report.workflow_name is None
        assert report.node_name is None

    def test_three_part_long_name_is_split(self):
        """A canonical ``nipype_pt_x.workflow.node`` name is split in two.

        Only the second and third dotted segments are meaningful: the workflow
        name and the node name respectively.
        """
        report = WorkflowReport(long_name="nipype_pt_x.my_workflow.my_node")
        assert report.workflow_name == "my_workflow"
        assert report.node_name == "my_node"

    def test_two_part_long_name_is_not_split(self):
        """Only an exact 3-part name assigns a workflow name.

        A 2-part string keeps ``workflow_name`` ``None`` and is used verbatim
        as the node name.
        """
        report = WorkflowReport(long_name="only.two")
        assert report.workflow_name is None
        assert report.node_name == "only.two"

    def test_single_part_long_name_becomes_node_name(self):
        """A name with no divider is used as-is for the node name."""
        report = WorkflowReport(long_name="single")
        assert report.workflow_name is None
        assert report.node_name == "single"

    def test_four_part_long_name_is_not_split(self):
        """More than three segments is not the canonical shape, so it is kept whole."""
        report = WorkflowReport(long_name="a.b.c.d")
        assert report.workflow_name is None
        assert report.node_name == "a.b.c.d"

    def test_info_and_crash_file_are_stored(self):
        """The optional ``info`` and ``crash_file`` payloads are passed through."""
        report = WorkflowReport(
            signal_type=WorkflowSignals.NODE_ERROR,
            long_name="nipype_pt_x.wf.node",
            info="out of memory",
            crash_file="/tmp/crash.pklz",
        )
        assert report.info == "out of memory"
        assert report.crash_file == "/tmp/crash.pklz"

    def test_defaults_for_optional_fields(self):
        """``info`` and ``crash_file`` default to ``None`` when omitted."""
        report = WorkflowReport()
        assert report.info is None
        assert report.crash_file is None
