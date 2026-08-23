from swane.utils.fsl_conflict_handler import fsl_conflict_check


def main():
    import sys
    import os
    import psutil
    from swane import strings
    import swane_supplement
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon, QPixmap
    from swane.ui.MainWindow import MainWindow
    from swane.config.ConfigManager import ConfigManager
    from swane import EXIT_CODE_REBOOT
    from swane.config.config_enums import GlobalPrefCategoryList
    from swane.utils.last_pid_is_running import last_pid_is_running
    from swane.utils.linux_desktop_integration import ensure_desktop_entry

    # Exit Code definition for automatic reboot
    current_exit_code = EXIT_CODE_REBOOT

    while current_exit_code == EXIT_CODE_REBOOT:

        # Singleton for SWANe application
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()

        # SWANe Icon definition
        app.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
        # Desktop file name definition, needed on Linux/Wayland to match the running
        # window to the .desktop entry installed by ensure_desktop_entry() below, so
        # that the taskbar/dock shows the SWANe icon instead of a generic one
        app.setDesktopFileName("swane")
        # SWANe App Name definition
        app.setApplicationDisplayName(strings.APPNAME)
        # Install/refresh the Linux .desktop entry so taskbar/dock show the SWANe icon
        ensure_desktop_entry(swane_supplement.appIcon_file)

        # SWANe Configuration loading
        global_config = ConfigManager()

        # Guard to prevent multiple SWANe instances launch
        last_pid, last_pid_create_time = global_config.get_last_pid()

        if last_pid_is_running(last_pid, last_pid_create_time):
            msg_box = QMessageBox()
            msg_box.setText(strings.main_multiple_instances_error)
            msg_box.exec()
            sys.exit(-1)

        current_process = psutil.Process(os.getpid())
        global_config[GlobalPrefCategoryList.MAIN]["last_pid"] = str(
            current_process.pid
        )
        global_config[GlobalPrefCategoryList.MAIN]["last_pid_create_time"] = str(
            current_process.create_time()
        )
        global_config.save()

        # MainWindow in a variable to prevent garbage collector deletion (might cause crash)
        try:
            widget = MainWindow(global_config)
            widget.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
            current_exit_code = app.exec()
        finally:
            # At SWANe exit
            # Clearing last PID and create time to allow new SWANe instance launch
            try:
                global_config[GlobalPrefCategoryList.MAIN]["last_pid"] = ""
                global_config[GlobalPrefCategoryList.MAIN]["last_pid_create_time"] = ""
                global_config.save()
            except Exception:
                pass

    sys.exit(current_exit_code)


if __name__ == "__main__":

    import sys

    # Standalone command to immediately remove the Linux .desktop entry created by
    # ensure_desktop_entry(). Not required for normal cleanup after "pip uninstall
    # swane": the entry's launcher already self-removes itself and the entry the
    # first time it is run against a no-longer-existing SWANe executable. This is
    # only for users who want the menu entry gone right away.
    if "--remove-desktop-entry" in sys.argv:
        from swane.utils.linux_desktop_integration import remove_desktop_entry

        remove_desktop_entry()
        sys.exit(0)

    # Before GUI execution check for fsl/python/freesurfer error
    if fsl_conflict_check():
        main()
