import os
import psutil


import os
import psutil


def last_pid_is_running(last_pid: int, last_pid_create_time: float | None = None) -> bool:
    """
    Parameters
    ----------
    last_pid: int
        The last previous application launch process id
    last_pid_create_time: float | None
        The creation time of the last previous application launch process

    Returns
    -------
    True if a SWANe process with the expected PID and create time is running
    """
    try:
        last_pid = int(last_pid)
    except (TypeError, ValueError):
        return False

    if last_pid <= 0:
        return False

    if last_pid == os.getpid():
        return False

    try:
        process = psutil.Process(last_pid)

        if not process.is_running():
            return False

        if process.status() == psutil.STATUS_ZOMBIE:
            return False

        try:
            saved_create_time = float(last_pid_create_time)
        except (TypeError, ValueError):
            return False

        current_create_time = process.create_time()

        return abs(current_create_time - saved_create_time) < 1.0

    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied, ValueError):
        return False