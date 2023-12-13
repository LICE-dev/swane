from enum import IntEnum


class WorkflowSignals(IntEnum):
    NODE_STARTED = 0
    NODE_COMPLETED = 1
    NODE_ERROR = 2
    WORKFLOW_INSUFFICIENT_RESOURCES = 3
    WORKFLOW_STOP = 4
    INVALID_SIGNAL = -1


class WorkflowReport:

    NODE_MSG_DIVIDER = '.'

    def __init__(self, signal_type: WorkflowSignals = WorkflowSignals.NODE_STARTED, long_name: str = None, info: str = None):
        """

        Parameters
        ----------
        signal_type: int
            A signal type in SIGNAL_TYPES
        long_name: str
            Optional. The node longname.
        info: str
            Optional. An informative text. For future implementations.
        """

        if not isinstance(signal_type, WorkflowSignals):
            signal_type = WorkflowSignals.INVALID_SIGNAL
        self.signal_type = signal_type
        self.workflow_name = None
        self.node_name = None
        if long_name is not None:
            # Every longname is like "nipype_pt_x.workflow_name.node_name.message_type", we need second and third part
            split = long_name.split(WorkflowReport.NODE_MSG_DIVIDER)
            if len(split) == 3:
                self.workflow_name = split[1]
                long_name = split[2]
            self.node_name = long_name
        self.info = info
