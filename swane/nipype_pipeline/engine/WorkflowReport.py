class WorkflowReport:

    NODE_STARTED = 1
    NODE_COMPLETED = 2
    NODE_ERROR = 3
    WORKFLOW_INSUFFICIENT_RESOURCES = 4
    WORKFLOW_STOP = 5

    SIGNAL_TYPES = [NODE_STARTED, NODE_COMPLETED, NODE_ERROR, WORKFLOW_INSUFFICIENT_RESOURCES, WORKFLOW_STOP]

    NODE_MSG_DIVIDER = '.'

    def __init__(self, signal_type: int = WORKFLOW_STOP, long_name: str = None, info: str = None):
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
        if signal_type not in WorkflowReport.SIGNAL_TYPES:
            signal_type = WorkflowReport.WORKFLOW_STOP
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
