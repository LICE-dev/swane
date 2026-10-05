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

    :return: 'mac' if macOS, 'linux' if Linux, 'windows' if Windows,
        'other' otherwise
    """
    system = platform.system().lower()
    if system == "darwin":
        return "mac"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    else:
        return "other"


def is_mac() -> bool:
    """
    Check if the operating system is macOS.
    """
    return get_os_type() == "mac"


def is_windows() -> bool:
    """
    Check if the operating system is Windows.

    SWANe has a second switch, ``swane.patches.windows_compat.is_windows``
    (``os.name == "nt"``): it drives the Nipype runtime patches and the
    command-line quoting, and lives there because that module must not import
    anything from SWANe (it runs before Nipype is imported). This one drives
    the application-level choices (UI, folder name rules). Both answer True on
    Windows; tests simulating Windows patch the one their code path reads.
    """
    return get_os_type() == "windows"


def is_linux() -> bool:
    """
    Check if the operating system is Linux.
    """
    return get_os_type() == "linux"


def blank_spaces_allowed() -> bool:
    """
    Check if blank spaces are allowed in the main working directory, subject
    folder paths and subject names.

    FSL and FreeSurfer break on paths containing blank spaces, so SWANe rejects
    them. On Windows those tools do not exist natively, the command lines SWANe
    runs quote every path, and home folders often contain spaces
    (``C:\\Users\\Name Surname``), so blank spaces are allowed there. If FSL were
    a mandatory dependency (``dependency_policy.FSL_MANDATORY``), the strict rule
    would apply everywhere.

    :return: True on Windows when FSL is not mandatory, False otherwise
    """
    from swane.config import dependency_policy

    return is_windows() and not dependency_policy.FSL_MANDATORY
