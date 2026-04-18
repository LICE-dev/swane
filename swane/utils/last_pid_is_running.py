import os
import psutil


import os
import psutil


import os
import psutil


def last_pid_is_running(last_pid: int, last_pid_create_time: float | None = None) -> bool:
    """
    Determines whether the previously stored SWANe process is still running.

    This function performs a robust check to avoid false positives caused by PID reuse.
    On most operating systems, a PID can be reassigned to a new process after the original
    one has terminated. Therefore, checking only the PID is not sufficient.

    The validation is done in multiple steps:

    1. Validate PID format
       - Ensure the PID is a valid integer > 0.
       - If invalid, assume no running instance.

    2. Avoid self-detection
       - If the stored PID matches the current process PID, return False.
       - This prevents detecting the current instance as a duplicate.

    3. Check if a process with that PID exists
       - If the process does not exist → return False.
       - If it exists but is not running or is a zombie → return False.

    4. Validate process identity using creation time
       - Convert stored creation time to float.
       - Retrieve current process creation time via psutil.
       - Compare both values.

       This step ensures that:
       - The PID has NOT been reused by another process.
       - We are still referring to the original SWANe instance.

       The comparison uses a tolerance of 1 second to account for:
       - Floating point precision differences
       - OS-level rounding differences

    Returns
    -------
    bool
        True if the original SWANe process is still running.
        False otherwise.
    """

    # Step 1: Validate PID
    try:
        last_pid = int(last_pid)
    except (TypeError, ValueError):
        return False

    if last_pid <= 0:
        return False

    # Step 2: Avoid matching current process
    if last_pid == os.getpid():
        return False

    try:
        # Step 3: Check process existence
        process = psutil.Process(last_pid)

        if not process.is_running():
            return False

        if process.status() == psutil.STATUS_ZOMBIE:
            return False

        # Step 4: Validate creation time (anti PID reuse)
        try:
            saved_create_time = float(last_pid_create_time)
        except (TypeError, ValueError):
            return False

        current_create_time = process.create_time()

        # If creation times match (within tolerance), it's the same process
        return abs(current_create_time - saved_create_time) < 1.0

    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied, ValueError):
        return False