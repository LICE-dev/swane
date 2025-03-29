import shutil
import platform

def is_command_available(command: str) -> bool:
    """
    Check if a command exists in the system PATH.

    :param command: Name of the command to check
    :return: True if the command exists, False otherwise
    """
    return shutil.which(command) is not None

def get_os_type() -> str:
    """
    Get the operating system type.

    :return: 'mac' if macOS, 'linux' if Linux, 'other' otherwise
    """
    system = platform.system().lower()
    if system == "darwin":
        return "mac"
    elif system == "linux":
        return "linux"
    else:
        return "other"

def is_mac() -> bool:
    """
    Check if the operating system is macOS.
    """
    return get_os_type() == "mac"

def is_linux() -> bool:
    """
    Check if the operating system is Linux.
    """
    return get_os_type() == "linux"
