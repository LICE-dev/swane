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
    from swane.utils.ConfigManager import ConfigManager
    from swane import EXIT_CODE_REBOOT

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
        # SWANe App Name definition
        app.setApplicationDisplayName(strings.APPNAME)
        
        # SWANe Configuration loading
        global_config = ConfigManager()

        # Guard to prevent multiple SWANe instances launch
        last_pid = global_config.getint('MAIN', 'lastPID')
        if last_pid != os.getpid():
            try:
                psutil.Process(last_pid)
                msg_box = QMessageBox()
                msg_box.setText(strings.main_multiple_instances_error)
                msg_box.exec()
                break

            except (psutil.NoSuchProcess, ValueError):
                global_config['MAIN']['lastPID'] = str(os.getpid())
                global_config.save()

        # MainWindow in a varariable to prenvent garbage collector deletion (might cause crash)
        widget = MainWindow(global_config)
        widget.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
        current_exit_code = app.exec()

    sys.exit(current_exit_code)


if __name__ == "__main__":

    # Before GUI execution check for fsl/python/freesurfer error
    if fsl_conflict_check():
        main()
