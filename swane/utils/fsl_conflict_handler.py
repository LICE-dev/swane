import os
import sys
from swane import strings
import subprocess
from swane.utils.platform_and_tools_utils import is_command_available, is_linux, is_mac


FSL_CONFLICT_PATH = "fsl/bin"
FREESURFER_CONFIG_FILE = "SetUpFreeSurfer.sh"
SHELL_PROFILE = {'sh': ['.profile'],
                 'bash': ['.bash_profile', '.profile', '.bashrc'],
                 'dash': ['.bash_profile', '.profile'],
                 'zsh': ['.zprofile', '.zshrc'],
                 'csh': ['.cshrc'],
                 'tcsh': ['.tcshrc']}

FIX_LINE = r"""PATH=$(echo "$PATH" | sed -e "s/:$( echo "$FSL_DIR" | sed 's/\//\\\//g')\/bin//")"""
APP_EXEC_COMMAND = "python3 -m " + __name__.split(".")[0]


def check_config_file(config_file: str):
    try:
        with open(config_file) as file:
            file_content = file.read()
        return FREESURFER_CONFIG_FILE in file_content
    except:
        return False


def get_config_file():
    # Try to identify user shell configuration file with fsl/freesurfer setup
    try:
        shell = os.path.basename(os.environ.get('SHELL', 'sh')).lower()
        home_dir = os.path.expanduser('~')

        if shell not in SHELL_PROFILE:
            shell = 'sh'

        candidates = [os.path.join(home_dir, p) for p in SHELL_PROFILE[shell]]
        for candidate in candidates:
            if check_config_file(candidate):
                return candidate

        return strings.generic_shell_file

    except KeyError:
        return strings.generic_shell_file


def runtime_fix():
    cmd = FIX_LINE + ";" + APP_EXEC_COMMAND
    subprocess.run(cmd, shell=True)


def config_file_fix(config_file: str):
    with open(config_file, "a") as file_object:
        file_object.write("\n"+FIX_LINE)


def copy_fix_to_clipboard():
    # Linux shell copy command
    if is_linux():
        subprocess.run("xclip -selection c", shell=True, text=True, input=FIX_LINE)
    # MacOS shell copy command
    if is_mac():
        subprocess.run("pbcopy", shell=True, text=True, input=FIX_LINE)


def fsl_conflict_check() -> bool:
    """
        Handle freesurfer<=7.3.2 overwriting system python executable if fsl>=6.0.6 is installed
        In that case propose a fix

    Returns
    -------
        True if system Python is unaffected, False if it was hidden

    """

    if FSL_CONFLICT_PATH not in sys.executable:
        return True

    # This function uses fsl built-in qt library to show a warning: ignore IDE import error!
    from PyQt5.QtWidgets import QApplication, QMessageBox

    app = QApplication([])
    app.setApplicationDisplayName(strings.APPNAME)

    config_file = get_config_file()
    error_string = strings.fsl_python_error % config_file

    msg_box = QMessageBox()
    msg_box.setText(error_string)
    msg_box.setInformativeText(FIX_LINE)
    msg_box.setIcon(QMessageBox.Warning)
    msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.Retry | QMessageBox.Cancel)
    msg_box.button(QMessageBox.Yes).setText(strings.fsl_python_error_fix)
    msg_box.button(QMessageBox.Retry).setText(strings.fsl_python_error_restart)
    
    if is_command_available('xclip') or is_mac():
        msg_box.button(QMessageBox.Cancel).setText(strings.fsl_python_error_exit)
        msg_box.setDefaultButton(QMessageBox.Cancel)
    ret = msg_box.exec()

    if ret == QMessageBox.Retry:
        runtime_fix()
    elif ret == QMessageBox.Yes:
        config_file_fix(config_file)
        runtime_fix()
    elif ret == QMessageBox.Cancel and (is_command_available('xclip') or is_mac()):
        copy_fix_to_clipboard()

    return False
