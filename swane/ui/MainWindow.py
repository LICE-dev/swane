from PySide6.QtWidgets import (QMainWindow, QMessageBox, QFileDialog, QInputDialog, QStyle,
                               QLineEdit, QTabWidget, QGridLayout, QLabel, QSizePolicy,
                               QSpacerItem, QWidget, QTabBar, QDialog, QPushButton, QStyleOptionButton)
from PySide6.QtGui import QAction, QIcon, QPixmap, QFont, QCloseEvent
from PySide6.QtCore import QCoreApplication, Qt, QThreadPool
from PySide6.QtSvgWidgets import QSvgWidget
import os
from swane.utils.DependencyManager import DependencyManager, Dependence, DependenceStatus
from swane.ui.PtTab import PtTab
from swane.ui.PreferencesWindow import PreferencesWindow
import swane_supplement
from swane import __version__, EXIT_CODE_REBOOT, strings
from swane.ui.workers.UpdateCheckWorker import UpdateCheckWorker
from swane.utils.Patient import Patient, PatientRet


class MainWindow(QMainWindow):
    """
    Custom implementation of PySide QMainWindow to define SWANe GUI.

    """
       
    def __init__(self, global_config):

        super(MainWindow, self).__init__()

        # GUI configuration setting
        self.global_config = global_config
        self.dependency_manager = DependencyManager()
        self.global_config.check_dependencies(self.dependency_manager)

        # GUI Icons setting
        self.setWindowIcon(QIcon(QPixmap(swane_supplement.appIcon_file)))
        self.OK_ICON_FILE = swane_supplement.okIcon_file
        self.ERROR_ICON_FILE = swane_supplement.errorIcon_file
        self.WARNING_ICON_FILE = swane_supplement.warnIcon_file
        self.LOADING_MOVIE_FILE = swane_supplement.loadingMovie_file
        self.VOID_SVG_FILE = swane_supplement.voidsvg_file
        self.OK_ICON = QPixmap(self.OK_ICON_FILE)
        self.ERROR_ICON = QPixmap(self.ERROR_ICON_FILE)
        self.WARNING_ICON = QPixmap(self.WARNING_ICON_FILE)
        self.NON_UNICODE_BUTTON_HEIGHT = MainWindow.get_non_unicode_height()

        # Patient folder configuration checking
        while self.global_config.get_patients_folder() == "":
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_choose_working_dir)
            msg_box.exec()
            self.set_patients_folder()

        # Patient folder configuration setting
        os.chdir(self.global_config.get_patients_folder())

        self.initialize_ui()

        # Check for update
        update_thread = UpdateCheckWorker()
        update_thread.signal.last_available.connect(lambda pip_version: self.update_available(pip_version))
        QThreadPool.globalInstance().start(update_thread)

    def update_available(self, pip_version: str):
        """
        Called if UpdateCheckWorker detect a newer version on pip
        Parameters
        ----------
        pip_version: str
            The version of the update available on pip
        """
        msg_box = QMessageBox(parent=self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(strings.mainwindow_update_available % pip_version)
        msg_box.exec()

    @staticmethod
    def get_non_unicode_height():
        button = QPushButton()
        opt = QStyleOptionButton()
        opt.initFrom(button)
        text_size = button.fontMetrics().size(Qt.TextShowMnemonic, button.text())
        return button.style().sizeFromContents(QStyle.CT_PushButton, opt, text_size, button).height()

    def open_pt_tab(self, patient: Patient):
        """
        Load a checked and valid patient folder.

        Parameters
        ----------
        patient : str
            The patient to load in the tab.

        Returns
        -------
        None.

        """
        
        this_tab = PtTab(self.global_config, patient, main_window=self, parent=self.main_tab)
        self.pt_tabs_array.append(this_tab)

        self.main_tab.addTab(this_tab, os.path.basename(patient.name))
        self.main_tab.setCurrentWidget(this_tab)
        
        this_tab.load_pt()

    def check_pt_limit(self) -> bool:
        """
        Check if SWANe can open another patient tab without overcome the limit set by configuration.

        Returns
        -------
        bool
            True if SWANe can load another tab, otherwise False.

        """
        
        max_pt = self.global_config.get_max_pt()
        if max_pt <= 0:
            return True
        if len(self.pt_tabs_array) >= max_pt:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setText(strings.mainwindow_max_pt_error)
            msg_box.exec()
            return False
        return True

    def search_pt_dir(self, button_state: bool = False, folder_path: str = None):
        """
        Try to open a patient directory

        Parameters
        ----------
        button_state: bool
            Not used, passed by QPushButton. Default is False
        folder_path: str
            The folder to load. Default is None

        Returns
        -------
        None.

        """
        
        # Guard to avoid the opening of patient tabs greater than the maximum allowed
        if not self.check_pt_limit():
            return

        if folder_path is None:
            # Open the directory selection dialog if a path is not provided
            file_dialog = QFileDialog()
            file_dialog.setDirectory(self.global_config.get_patients_folder())
            folder_path = file_dialog.getExistingDirectory(self, strings.mainwindow_select_pt_folder)

        patient = Patient(self.global_config)

        # Guard to avoid an already loaded patient directory
        for pt in self.pt_tabs_array:
            if pt.pt_folder == folder_path:
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setText(strings.mainwindow_pt_already_loaded_error)
                msg_box.exec()
                return

        patient_load_ret = patient.load(folder_path, self.dependency_manager)

        if patient_load_ret == PatientRet.ValidFolder:
            self.open_pt_tab(patient)
        elif patient_load_ret == PatientRet.FolderNotFound:
            # Should not be possible
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setText(strings.mainwindow_ptfolder_not_found_error)
            msg_box.exec()
            return
        elif patient_load_ret == PatientRet.PathBlankSpaces:
            # Guard to avoid the opening a directory containing blank spaces
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setText(strings.mainwindow_ptfolder_with_blank_spaces_error)
            msg_box.exec()
            return
        elif patient_load_ret == PatientRet.FolderOutsideMain:
            # Guard to avoid the opening of a directory outside the main patient folder
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setText(strings.mainwindow_ptfolder_outside_workingdir_error)
            msg_box.exec()
            return
        elif patient_load_ret == PatientRet.InvalidFolderTree:
            # Check if selected folder is a valid patient folder
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setText(strings.mainwindow_invalid_folder_error)
            msg_box.exec()

            msg_box2 = QMessageBox()
            msg_box2.setText(strings.mainwindow_force_dir_update)
            msg_box2.setIcon(QMessageBox.Icon.Question)
            msg_box2.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box2.button(QMessageBox.StandardButton.Yes).setText("Yes")
            msg_box2.button(QMessageBox.StandardButton.No).setText("No")
            msg_box2.setDefaultButton(QMessageBox.StandardButton.No)
            ret = msg_box2.exec()

            # A patient folder has a predefined folder tree.
            # SWANe recognizes a patient folder checking its subfolders.
            # If a selected folder is not valid, the user may force its conversion into a patient folder.
            if ret == QMessageBox.StandardButton.Yes:
                patient.update_pt_dir(folder_path)
                self.search_pt_dir(folder_path=folder_path)
            return
            
        return

    def get_suggested_patient_name(self) -> str:
        """
        Get a default name for the patient folder based the existing patient folders into the main patient directory.

        Returns
        -------
        str
            The suggested patient folder name.

        """
        
        import re
        
        regex = re.compile('^' + self.global_config.get_patients_prefix() + '\d+$')
        file_list = []
        
        for this_dir in os.listdir(self.global_config.get_patients_folder()):
            if regex.match(this_dir):
                file_list.append(
                    int(this_dir.replace(self.global_config.get_patients_prefix(), "")))

        if len(file_list) == 0:
            return self.global_config.get_patients_prefix() + "1"
        
        return self.global_config.get_patients_prefix() + str(max(file_list) + 1)

    def choose_new_pt_dir(self):
        """
        Create a new patient folder. The user must specify its name.

        Returns
        -------
        None.

        """
        
        if not self.check_pt_limit():
            return

        text, ok = QInputDialog.getText(self, strings.mainwindow_new_pt_title, strings.mainwindow_new_pt_name,
                                        QLineEdit.EchoMode.Normal, self.get_suggested_patient_name())

        if not ok:
            return

        pt_name = str(text)

        if pt_name == "":
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_new_pt_name_error + pt_name)
            msg_box.exec()
            return

        if os.path.exists(os.path.join(self.global_config.get_patients_folder(), pt_name)):
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_pt_exists_error + pt_name)
            msg_box.exec()
            return

        self.create_new_pt_dir(pt_name.replace(" ", "_"))

    def set_patients_folder(self):
        """
        Generates the OS directory selection dialog to set the default patient folder

        Returns
        -------
        None.

        """
        
        folder_path = QFileDialog.getExistingDirectory(self, strings.mainwindow_choose_working_dir_title)
        
        if not os.path.exists(folder_path):
            return

        if ' ' in folder_path:
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_working_dir_space_error)
            msg_box.exec()
            return
        
        self.global_config.set_patients_folder(os.path.abspath(folder_path))
        
        os.chdir(folder_path)

    def create_new_pt_dir(self, pt_name: str):
        """
        Create a new patient folder and subfolders.

        Parameters
        ----------
        pt_name : str
            The patient folder name.

        Returns
        -------
        None.

        """

        patient = Patient(self.global_config)
        if patient.create_new_pt_dir(pt_name):
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_new_pt_created + pt_name)
            msg_box.exec()
            self.open_pt_tab(patient)

    def edit_config(self):
        """
        Open the Global Preferences Window.

        Returns
        -------
        None.

        """
        
        if self.check_running_workflows():
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_pref_disabled_error)
            msg_box.exec()
            return

        preference_window = PreferencesWindow(self.global_config, self.dependency_manager, False)
        ret = preference_window.exec()
        
        if ret == EXIT_CODE_REBOOT:
            self.close()
            QCoreApplication.exit(EXIT_CODE_REBOOT)
            
        if ret != 0:
            self.reset_workflows()

    def edit_wf_config(self):
        """
        Open the Default Workflow Settings Window.

        Returns
        -------
        None.

        """

        if self.check_running_workflows():
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_pref_disabled_error)
            msg_box.exec()
            return

        wf_preference_window = PreferencesWindow(self.global_config, self.dependency_manager, True)
        ret = wf_preference_window.exec()

        if ret == -1:
            self.global_config.load_default_wf_settings(save=True)
            self.edit_wf_config()

    def check_running_workflows(self) -> bool:
        """
        Check if SWANe is executing a workflow in any open Patients tab.

        Returns
        -------
        bool
            True if SWANe is executing a workflow, otherwise False.

        """
        
        for pt in self.pt_tabs_array:
            if pt.is_workflow_process_alive():
                return True
            
        return False

    def reset_workflows(self):
        """
        Reset all the generated workflows that are not already running.

        Returns
        -------
        None.

        """
        
        for pt in self.pt_tabs_array:
            pt.reset_workflow()

    def about(self):
        """
        Open the About Window.

        Returns
        -------
        None.

        """
        
        about_dialog = QDialog(parent=self)
        layout = QGridLayout()

        bold_font = QFont()
        bold_font.setBold(True)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() * 1.5)

        label_about1 = QLabel(strings.APPNAME)
        label_about1.setFont(title_font)
        label_about2 = QLabel(strings.app_acronym)
        label_about3 = QLabel("Version: " + __version__)

        label_about4 = QLabel(strings.aboutwindow_python_libs)

        label_about_icon = QLabel()
        icon = QPixmap(swane_supplement.appIcon_file)

        label_about_icon.setPixmap(icon.scaled(60, 60))

        layout.addWidget(label_about1, 0, 1)
        layout.addWidget(label_about2, 1, 1)
        layout.addWidget(label_about3, 2, 1)
        layout.addWidget(label_about4, 3, 1)

        layout.addWidget(label_about_icon, 0, 0, 3, 1)

        about_dialog.setLayout(layout)
        about_dialog.exec()

    def initialize_ui(self):
        """
        Generates the SWANE GUI

        Returns
        -------
        None.

        """
        
        self.resize(800, 600)
        self.setWindowTitle(strings.APPNAME + " - " + strings.app_acronym)

        self.statusBar().showMessage('')

        # Buttons definition
        button_action = QAction(QIcon.fromTheme(
            "document-open"), strings.menu_load_pt, self)
        button_action.setStatusTip(strings.menu_load_pt_tip)
        button_action.triggered.connect(self.search_pt_dir)

        button_action2 = QAction(QIcon.fromTheme(
            "document-new"), strings.menu_new_pt, self)
        button_action2.setStatusTip(strings.menu_new_pt_tip)
        button_action2.triggered.connect(self.choose_new_pt_dir)

        button_action3 = QAction(QIcon.fromTheme(
            "application-exit"), strings.menu_exit, self)
        button_action3.triggered.connect(self.close)

        button_action4 = QAction(QIcon.fromTheme(
            "preferences-other"), strings.menu_pref, self)
        button_action4.setStatusTip(strings.menu_pref_tip)
        button_action4.triggered.connect(self.edit_config)

        button_action5 = QAction(QIcon.fromTheme(
            "preferences-other"), strings.menu_wf_pref, self)
        button_action5.triggered.connect(self.edit_wf_config)

        button_action7 = QAction(strings.menu_about, self)
        button_action7.triggered.connect(self.about)

        # Menu definition and population
        menu = self.menuBar()
        menu.setNativeMenuBar(False)
        file_menu = menu.addMenu(strings.menu_file_name)
        file_menu.addAction(button_action)
        file_menu.addAction(button_action2)
        file_menu.addAction(button_action3)
        tool_menu = menu.addMenu(strings.menu_tools_name)
        tool_menu.addAction(button_action4)
        tool_menu.addAction(button_action5)
        help_menu = menu.addMenu(strings.menu_help_name)
        help_menu.addAction(button_action7)
        
        # Tab definition
        self.main_tab = QTabWidget(parent=self)
        self.main_tab.setTabsClosable(True)
        self.main_tab.tabCloseRequested.connect(self.close_pt_tab)
        self.setCentralWidget(self.main_tab)
        self.homeTab = QWidget()
        self.main_tab.addTab(self.homeTab, strings.mainwindow_home_tab_name)

        # Tab closing option disabled
        self.main_tab.tabBar().setTabButton(0, QTabBar.ButtonPosition.LeftSide, None)
        self.main_tab.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        
        # Home Tab definition
        self.home_tab_ui()
        
        self.pt_tabs_array = []

        self.show()

    def close_pt_tab(self, index: int):
        """
        Handle the PySide tab closing event for the Patient tab.

        Parameters
        ----------
        index : int
            The patient tab index into the GUI.

        Returns
        -------
        None.

        """
        
        # Guard to prevent the Home Tab closing
        if index <= 0:
            return

        tab_item = self.main_tab.widget(index)
        if tab_item.is_workflow_process_alive():
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_wf_executing_error_1)
            msg_box.exec()
            return

        tab_item.patient.config.save()
        
        self.pt_tabs_array.remove(tab_item)
        self.main_tab.removeTab(index)

    def closeEvent(self, event: QCloseEvent):
        """
        Prevent the closing of a running workflow tab

        Parameters
        ----------
        event : QCloseEvent
            PySide QCloseEvent.

        Returns
        -------
        None.

        """
        
        if not self.check_running_workflows():
            event.accept()
        else:
            msg_box = QMessageBox()
            msg_box.setText(strings.mainwindow_wf_executing_error_2)
            msg_box.exec()
            event.ignore()

    def home_tab_ui(self):
        """
        Generates the Home Tab layout

        Returns
        -------
        None.

        """
        
        self.home_grid_layout = QGridLayout()

        bold_font = QFont()
        bold_font.setBold(True)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() * 1.5)
        x = 0

        label_welcome1 = QLabel(strings.mainwindow_home_label1)
        label_welcome1.setFont(title_font)
        label_welcome2 = QLabel(strings.mainwindow_home_label2)
        label_welcome2.setWordWrap(True)
        label_welcome3 = QLabel(strings.mainwindow_home_label3)
        label_welcome3.setWordWrap(True)
        label_welcome4 = QLabel(strings.mainwindow_home_label4)
        label_welcome4.setFont(bold_font)

        self.home_grid_layout.addWidget(label_welcome1, x, 0, 1, 2)
        x += 1
        self.home_grid_layout.addWidget(label_welcome2, x, 0, 1, 2)
        x += 1
        self.home_grid_layout.addWidget(label_welcome3, x, 0, 1, 2)
        x += 1
        self.home_grid_layout.addWidget(label_welcome4, x, 0, 1, 2)
        x += 1

        # Main window dependency check
        label_main_dep = QLabel(strings.mainwindow_home_label5)
        label_main_dep.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        label_main_dep.setFont(bold_font)
        self.home_grid_layout.addWidget(label_main_dep, x, 0, 1, 2)
        x += 1

        x = self.add_home_entry(self.dependency_manager.dcm2niix, x)

        x = self.add_home_entry(self.dependency_manager.fsl, x)

        label_main_dep = QLabel(strings.mainwindow_home_label6)
        label_main_dep.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        label_main_dep.setFont(bold_font)
        self.home_grid_layout.addWidget(label_main_dep, x, 0, 1, 2)
        x += 1

        x = self.add_home_entry(self.dependency_manager.freesurfer, x)
        self.global_config.freesurfer = self.dependency_manager.is_freesurfer()

        if DependencyManager.need_slicer_check(self.global_config):
            self.slicer_x = x
            x = self.add_home_entry(Dependence(DependenceStatus.CHECKING, strings.mainwindow_dep_slicer_src), x)
            DependencyManager.check_slicer(self.global_config.get_slicer_path(), self.slicer_row)
        else:
            label = strings.check_dep_slicer_found % self.global_config.get_slicer_version()
            x = self.add_home_entry(Dependence(DependenceStatus.DETECTED, label), x)

        label_main_dep = QLabel(strings.mainwindow_home_label7)
        label_main_dep.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        label_main_dep.setFont(bold_font)
        self.home_grid_layout.addWidget(label_main_dep, x, 0, 1, 2)
        x += 1

        x = self.add_home_entry(self.dependency_manager.graphviz, x)

        vertical_spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.home_grid_layout.addItem(vertical_spacer, x, 0, 1, 2)

        self.homeTab.setLayout(self.home_grid_layout)

    def add_home_entry(self, dep: Dependence, x: int) -> int:
        """
        Generates a dependency check label, adding it to an existing layout

        Parameters
        ----------
        dep : Dependence
            A Dependence object to be parsed.
        x : int
            The starting grid layout row index.

        Returns
        -------
        int
            The next grid layout row index.

        """
        
        label_icon = QLabel()
        label_icon.setScaledContents(True)

        if dep.state == DependenceStatus.DETECTED:
            label_icon.setPixmap(self.OK_ICON)
        elif dep.state == DependenceStatus.WARNING:
            label_icon.setPixmap(self.WARNING_ICON)
        elif dep.state == DependenceStatus.CHECKING:
            label_icon = QSvgWidget()
            label_icon.load(self.LOADING_MOVIE_FILE)
        else:
            label_icon.setPixmap(self.ERROR_ICON)

        label_icon.setFixedSize(25, 25)

        old_icon_layout = self.home_grid_layout.itemAtPosition(x, 0)
        if old_icon_layout is not None:
            old_icon_layout.widget().deleteLater()
            self.home_grid_layout.removeItem(old_icon_layout)
        self.home_grid_layout.addWidget(label_icon, x, 0)

        label = QLabel(dep.label)
        label.setOpenExternalLinks(True)
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        old_label_layout = self.home_grid_layout.itemAtPosition(x, 1)
        if old_label_layout is not None:
            old_label_layout.widget().deleteLater()
            self.home_grid_layout.removeItem(old_label_layout)
        self.home_grid_layout.addWidget(label, x, 1)
        
        return x + 1

    def slicer_row(self, slicer_path: str, slicer_version: str, msg: str, state: DependenceStatus):
        """
        Generates the Slicer dependency check label and path, if 3D Slicer is found.

        Parameters
        ----------
        slicer_path : str
            The local 3D Slicer path.
        slicer_version: str
            The Slicer version found
        msg : str
            The label message.
        state: DependenceStatus
            A state from DependenceStatus.

        Returns
        -------
        None.

        """
        
        self.add_home_entry(Dependence(state, msg), self.slicer_x)

        self.global_config.set_slicer_path(slicer_path)
        self.global_config.set_slicer_version(slicer_version)
        self.global_config.save()

        for tab in self.pt_tabs_array:
            tab.export_results_button_update_state()
            tab.load_scene_button_update_state()
