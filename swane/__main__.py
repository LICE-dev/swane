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

    current_exit_code = EXIT_CODE_REBOOT

    while current_exit_code == EXIT_CODE_REBOOT:

        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()

        app.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
        app.setApplicationDisplayName(strings.APPNAME)

        global_config = ConfigManager()

        # single instance check
        last_pid = global_config.getint('MAIN', 'lastPID')
        if last_pid != os.getpid():
            try:
                psutil.Process(last_pid)
                msg_box = QMessageBox()
                msg_box.setText("Another instance of " + strings.APPNAME + " is already running!")
                msg_box.exec()
                break

            except (psutil.NoSuchProcess, ValueError):
                global_config['MAIN']['lastPID'] = str(os.getpid())
                global_config.save()

        # save MainWindow in a var to keep in memory and prevent crash
        widget = MainWindow(global_config)
        widget.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
        current_exit_code = app.exec()

    sys.exit(current_exit_code)


if __name__ == "__main__":

    # before gui execution check for fsl/python/freesurfer error
    if fsl_conflict_check():
        main()
