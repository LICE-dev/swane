import os
import psutil


def last_pid_is_running(last_pid: int) -> bool:
    """

    Parameters
    ----------
    last_pid: int
        The last previous application launch process id

    Returns
    -------
    True if a process with PID=lòast_pid is running
    """
    try:
        return last_pid != os.getpid() and psutil.Process(last_pid)
    except (psutil.NoSuchProcess, ValueError):
        pass
    return False
