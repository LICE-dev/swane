import os
import pydicom
from PySide6.QtCore import Qt, QThreadPool, QFileSystemWatcher
from PySide6.QtGui import QFont
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QTabWidget, QWidget, QGridLayout, QLabel, QHeaderView,
                               QPushButton, QSizePolicy, QHBoxLayout, QSpacerItem,
                               QGroupBox, QVBoxLayout, QMessageBox, QListWidget,
                               QFileDialog, QTreeWidget, QErrorMessage, QFileSystemModel,
                               QTreeView, QComboBox)

from swane import strings
from swane.workers.SlicerExportWorker import SlicerExportWorker
from swane.workers.SlicerViewerWorker import load_scene
from swane.ui.CustomTreeWidgetItem import CustomTreeWidgetItem
from swane.ui.PersistentProgressDialog import PersistentProgressDialog
from swane.ui.PreferencesWindow import PreferencesWindow
from swane.ui.VerticalScrollArea import VerticalScrollArea
from swane.config.ConfigManager import ConfigManager
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.utils.DataInputList import DataInputList
from swane.utils.DependencyManager import DependencyManager
from swane.config.preference_list import WORKFLOW_TYPES
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
from swane.utils.Patient import Patient, PatientRet
from swane.workers.open_results_directory import open_results_directory


class PatientTab(QTabWidget):
    """
    Custom implementation of PySide QTabWidget to define a patient tab widget.

    """
    
    DATATAB = 0
    EXECTAB = 1
    RESULTTAB = 2

    def __init__(self, global_config: ConfigManager, patient: Patient, main_window, parent=None):
        super(PatientTab, self).__init__(parent)
        self.global_config = global_config
        self.patient = patient
        self.main_window = main_window

        self.data_tab = QWidget()
        self.exec_tab = QWidget()
        self.result_tab = QWidget()

        self.addTab(self.data_tab, strings.pttab_data_tab_name)
        self.addTab(self.exec_tab, strings.pttab_wf_tab_name)
        self.addTab(self.result_tab, strings.pttab_results_tab_name)

        self.directory_watcher = QFileSystemWatcher()
        self.directory_watcher.directoryChanged.connect(self.reset_workflow)

        self.scan_directory_watcher = QFileSystemWatcher()
        self.scan_directory_watcher.directoryChanged.connect(self.clear_scan_result)

        self.result_directory_watcher = QFileSystemWatcher()
        self.result_directory_watcher.directoryChanged.connect(self.result_directory_changed)

        self.workflow_process = None
        self.node_list = None
        self.input_report = {}
        self.dicom_scan_series_list = []
        self.importable_series_list = QListWidget()
        self.wf_type_combo = None
        self.node_button = None
        self.node_list_treeWidget = None
        self.patient_config_button = None
        self.exec_button = None
        self.exec_graph = None
        self.load_scene_button = None
        self.open_results_directory_button = None
        self.results_model = None
        self.result_tree = None
        self.generate_scene_button = None

        self.data_tab_ui()
        self.exec_tab_ui()
        self.result_tab_ui()

        self.setTabEnabled(PatientTab.EXECTAB, False)
        self.setTabEnabled(PatientTab.RESULTTAB, False)

    def update_node_list(self, wf_report: WorkflowReport):
        """
        Searches for the node linked to the msg arg.
        Uses the parsed msng arg to update the node status.

        Parameters
        ----------
        wf_report : WorkflowReport
            Workflow Monitor Worker message to parse.

        Returns
        -------
        None.

        """
        
        if wf_report.signal_type == WorkflowSignals.WORKFLOW_STOP:
            errors = False
            for key in self.node_list.keys():
                self.node_list[key].node_holder.setExpanded(False)
                if not self.node_list[key].node_holder.completed:
                    errors = True
                    for subkey in self.node_list[key].node_list.keys():
                        if self.node_list[key].node_list[subkey].node_holder.art == self.main_window.ERROR_ICON_FILE:
                            self.node_list[key].node_holder.set_art(self.main_window.ERROR_ICON_FILE)
                            break

            self.setTabEnabled(PatientTab.DATATAB, True)

            self.exec_button_setEnabled(False)

            if errors:
                self.node_button.setEnabled(True)
                self.patient.workflow = None
                self.exec_button.setText(strings.pttab_wf_executed_with_error)
                self.exec_button.setToolTip("")
            else:
                self.exec_button.setText(strings.pttab_wf_executed)
                self.exec_button.setToolTip("")

            self.enable_tab_if_result_dir()
            
            return
        elif wf_report.signal_type == WorkflowSignals.INVALID_SIGNAL:
            # Invalid signal sent from WF to UI, code error intercept
            try:
                self.workflow_process.stop_event.set()
            except:
                pass
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_wf_invalid_signal)
            msg_box.exec()


        # TODO - To be implemented for RAM usage info by each workflow
        # if msg == WorkflowProcess.WORKFLOW_INSUFFICIENT_RESOURCES:
        #     msg_box = QMessageBox()
        #     msg_box.setText(strings.pttab_wf_insufficient_resources)
        #     msg_box.exec()

        if wf_report.signal_type == WorkflowSignals.NODE_STARTED:
            icon = self.main_window.LOADING_MOVIE_FILE
        elif wf_report.signal_type == WorkflowSignals.NODE_COMPLETED:
            icon = self.main_window.OK_ICON_FILE
        else:
            icon = self.main_window.ERROR_ICON_FILE

        self.node_list[wf_report.workflow_name].node_list[wf_report.node_name].node_holder.set_art(icon)

        if wf_report.info is not None:
            self.node_list[wf_report.workflow_name].node_list[wf_report.node_name].node_holder.setToolTip(0, wf_report.info)

        self.node_list[wf_report.workflow_name].node_holder.setExpanded(True)

        if icon == self.main_window.OK_ICON_FILE:
            completed = True
            for key in self.node_list[wf_report.workflow_name].node_list.keys():
                if self.node_list[wf_report.workflow_name].node_list[key].node_holder.art != self.main_window.OK_ICON_FILE:
                    completed = False
                    break
            if completed:
                self.node_list[wf_report.workflow_name].node_holder.set_art(self.main_window.OK_ICON_FILE)
                self.node_list[wf_report.workflow_name].node_holder.setExpanded(False)
                self.node_list[wf_report.workflow_name].node_holder.completed = True

    def remove_running_icon(self):
        """
        Remove all the loading icons from the series labels.

        Returns
        -------
        None.

        """
        
        for key1 in self.node_list.keys():
            for key2 in self.node_list[key1].node_list.keys():
                if self.node_list[key1].node_list[key2].node_holder.art == self.main_window.LOADING_MOVIE_FILE:
                    self.node_list[key1].node_list[key2].node_holder.set_art(self.main_window.VOID_SVG_FILE)

    def data_tab_ui(self):
        """
        Generates the Data tab UI.

        Returns
        -------
        None.

        """
        
        # Horizontal Layout
        layout = QHBoxLayout()

        # First Column: INPUT LIST
        scroll_area = VerticalScrollArea()
        folder_layout = QGridLayout()
        scroll_area.m_scrollAreaWidgetContents.setLayout(folder_layout)

        bold_font = QFont()
        bold_font.setBold(True)
        x = 0

        for data_input in self.patient.input_state_list:
            self.input_report[data_input] = [QSvgWidget(self),
                                             QLabel(data_input.value.label),
                                             QLabel(""),
                                             QPushButton(strings.pttab_import_button),
                                             QPushButton(strings.pttab_clear_button)]
            self.set_error(data_input, "")
            if data_input.value.tooltip != "":
                # Add tooltips and append ⓘ character to label
                self.input_report[data_input][1].setText(data_input.value.label+" "+strings.INFOCHAR)
                self.input_report[data_input][1].setToolTip(data_input.value.tooltip)
            self.input_report[data_input][1].setFont(bold_font)
            self.input_report[data_input][1].setAlignment(Qt.AlignLeft | Qt.AlignBottom)
            self.input_report[data_input][2].setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.input_report[data_input][2].setStyleSheet("margin-bottom: 20px")
            self.input_report[data_input][3].clicked.connect(
                lambda checked=None, z=data_input: self.dicom_import_to_folder(z))
            self.input_report[data_input][3].setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.input_report[data_input][4].clicked.connect(
                lambda checked=None, z=data_input: self.clear_import_folder(z))
            self.input_report[data_input][4].setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            folder_layout.addWidget(self.input_report[data_input][0], (x * 2), 0, 2, 1)
            folder_layout.addWidget(self.input_report[data_input][1], (x * 2), 1)

            folder_layout.addWidget(self.input_report[data_input][3], (x * 2), 2)
            folder_layout.addWidget(self.input_report[data_input][4], (x * 2), 3)

            folder_layout.addWidget(self.input_report[data_input][2], (x * 2) + 1, 1, 1, 3)
            x += 1

        # Second Column: Series to be imported
        import_group_box = QGroupBox()
        import_layout = QVBoxLayout()
        import_group_box.setLayout(import_layout)

        scan_dicom_folder_button = QPushButton(strings.pttab_scan_dicom_button)
        scan_dicom_folder_button.clicked.connect(self.scan_dicom_folder)

        import_layout.addWidget(scan_dicom_folder_button)
        import_layout.addWidget(self.importable_series_list)

        # Adding data_input columns to Main Layout
        layout.addWidget(scroll_area, stretch=1)
        layout.addWidget(import_group_box, stretch=1)
        self.data_tab.setLayout(layout)

    def dicom_import_to_folder(self, data_input: DataInputList, force_mod: bool = False):
        """
        Copies the files inside the selected folder in the input list into the folder specified by data_input var.

        Parameters
        ----------
        data_input: DataInputList
            The name of the series to which couple the selected file.
        force_mod: bool
            Skip the modality check. Default is False

        Returns
        -------
        None.

        """
        
        if self.importable_series_list.currentRow() == -1:
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_selected_series_error)
            msg_box.exec()
            return

        copy_list = self.dicom_scan_series_list[self.importable_series_list.currentRow()][1]
        vols = self.dicom_scan_series_list[self.importable_series_list.currentRow()][3]
        found_mod = self.dicom_scan_series_list[self.importable_series_list.currentRow()][2].upper()

        progress = PersistentProgressDialog(strings.pttab_dicom_copy, 0, len(copy_list) + 1, self)
        self.set_loading(data_input)

        # Copy files and check for return
        import_ret = self.patient.dicom_import_to_folder(data_input=data_input,
                                                         copy_list=copy_list,
                                                         vols=vols,
                                                         mod=found_mod,
                                                         force_modality=force_mod,
                                                         progress_callback=progress.increase_value
                                                         )
        if import_ret != PatientRet.DataImportCompleted:
            if import_ret == PatientRet.DataImportErrorVolumesMax:
                msg_box = QMessageBox()
                msg_box.setText(strings.pttab_wrong_max_vols_check_msg % (vols, data_input.value.max_volumes))
                msg_box.exec()
            elif import_ret == PatientRet.DataImportErrorVolumesMin:
                msg_box = QMessageBox()
                msg_box.setText(strings.pttab_wrong_min_vols_check_msg % (vols, data_input.value.min_volumes))
                msg_box.exec()
            elif import_ret == PatientRet.DataImportErrorCopy:
                msg_box = QMessageBox()
                msg_box.setText(strings.pttab_import_copy_error_msg)
                msg_box.exec()
            elif import_ret == PatientRet.DataImportErrorModality:
                msg_box = QMessageBox()
                msg_box.setText(strings.pttab_wrong_type_check_msg % (found_mod, data_input.value.image_modality.value))
                msg_box.setInformativeText(strings.pttab_wrong_type_check)
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg_box.setDefaultButton(QMessageBox.StandardButton.No)
                ret = msg_box.exec()
                if ret == QMessageBox.StandardButton.Yes:
                    self.dicom_import_to_folder(data_input, force_mod=True)
            self.set_error(data_input, "")
            progress.deleteLater()
            return

        progress.setRange(0, 0)
        progress.setLabelText(strings.pttab_dicom_check)

        self.patient.check_input_folder(data_input, status_callback=self.input_check_update, progress_callback=progress.increase_value)
        self.reset_workflow()

    def scan_dicom_folder(self):
        """
        Opens a folder dialog window to select the DICOM files folder to import.
        Scans the folder in a new thread.

        Returns
        -------
        None.

        """
        
        folder_path = QFileDialog.getExistingDirectory(self, strings.pttab_select_dicom_folder)
        
        if not os.path.exists(folder_path):
            return

        dicom_src_work = DicomSearchWorker(folder_path)
        dicom_src_work.load_dir()

        if dicom_src_work.get_files_len() > 0:
            self.clear_scan_result()
            self.dicom_scan_series_list = []
            progress = PersistentProgressDialog(strings.pttab_dicom_scan, 0, 0, parent=self.parent())
            progress.show()
            progress.setMaximum(dicom_src_work.get_files_len())
            dicom_src_work.signal.sig_loop.connect(lambda i: progress.increase_value(i))
            dicom_src_work.signal.sig_finish.connect(self.show_scan_result)
            QThreadPool.globalInstance().start(dicom_src_work)

        else:
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_no_dicom_error + folder_path)
            msg_box.exec()

    def exec_tab_ui(self):
        """
        Generates the Execute Workflow tab UI.

        Returns
        -------
        None.

        """
        
        layout = QGridLayout()

        # First Column: NODE LIST
        self.wf_type_combo = QComboBox(self)

        for index, label in enumerate(WORKFLOW_TYPES):
            self.wf_type_combo.insertItem(index, label)

        layout.addWidget(self.wf_type_combo, 0, 0)

        self.node_button = QPushButton(strings.GENBUTTONTEXT)
        self.node_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.node_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.node_button.clicked.connect(self.gen_wf)

        layout.addWidget(self.node_button, 1, 0)

        self.node_list_treeWidget = QTreeWidget()
        self.node_list_treeWidget.setHeaderHidden(True)
        node_list_width = 320
        self.node_list_treeWidget.setFixedWidth(node_list_width)
        self.node_list_treeWidget.header().setMinimumSectionSize(node_list_width)
        self.node_list_treeWidget.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.node_list_treeWidget.header().setStretchLastSection(False)
        self.node_list_treeWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.node_list_treeWidget.horizontalScrollBar().setEnabled(True)

        layout.addWidget(self.node_list_treeWidget, 2, 0)
        self.node_list_treeWidget.itemClicked.connect(self.tree_item_clicked)

        # Second Column: Graphviz Graph Layout
        self.patient_config_button = QPushButton(strings.PTCONFIGBUTTONTEXT)
        self.patient_config_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.patient_config_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.patient_config_button.clicked.connect(self.edit_pt_config)
        layout.addWidget(self.patient_config_button, 0, 1)

        self.exec_button = QPushButton(strings.EXECBUTTONTEXT)
        self.exec_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.exec_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.exec_button.clicked.connect(self.toggle_workflow_execution)
        self.exec_button_setEnabled(False)

        layout.addWidget(self.exec_button, 1, 1)
        self.exec_graph = QSvgWidget()
        layout.addWidget(self.exec_graph, 2, 1)

        self.exec_tab.setLayout(layout)

    def edit_pt_config(self):
        """
        Opens the Patient Preference Window.

        Returns
        -------
        None.

        """

        preference_window = PreferencesWindow(self.patient.config, self.patient.dependency_manager, True, self)
        ret = preference_window.exec()
        if ret != 0:
            self.reset_workflow()
        if ret == -1:
            self.patient.config.load_default_workflow_settings(save=True)
            self.edit_pt_config()

    def on_wf_type_changed(self, index: int):
        """
        Updates the workflow at workflow type combo change.

        Parameters
        ----------
        index : int
            The new selected value from the Execution tab workflow type combo.

        Returns
        -------
        None.

        """
        
        self.patient.config.set_workflow_option(index)
        self.patient.config.save()
        self.reset_workflow()

    def gen_wf(self):
        """
        Generates and populates the Main Workflow.
        Shows the node list into the UI.
        Generates the graphviz analysis graphs on a new thread.

        Returns
        -------
        None.

        """
        
        generate_workflow_return = self.patient.generate_workflow()
        
        if generate_workflow_return == PatientRet.GenWfMissingFSL:
            error_dialog = QErrorMessage(parent=self)
            error_dialog.showMessage(strings.pttab_missing_fsl_error)
            return
        elif generate_workflow_return == PatientRet.GenWfError:
            error_dialog = QErrorMessage(parent=self)
            error_dialog.showMessage(strings.pttab_wf_gen_error)
            return
        
        self.node_list_treeWidget.clear()
        self.node_list = self.patient.workflow.get_node_array()
        
        # Graphviz analysis graphs drawing
        for node in self.node_list.keys():
            self.node_list[node].node_holder = CustomTreeWidgetItem(self.node_list_treeWidget, self.node_list_treeWidget, self.node_list[node].long_name)
            if len(self.node_list[node].node_list.keys()) > 0:                    
                for sub_node in self.node_list[node].node_list.keys():
                    self.node_list[node].node_list[sub_node].node_holder = CustomTreeWidgetItem(self.node_list[node].node_holder, self.node_list_treeWidget, self.node_list[node].node_list[sub_node].long_name)
        
        # UI updating
        self.exec_button_setEnabled(True)
        self.node_button.setEnabled(False)

    def tree_item_clicked(self, item, col: int):
        """
        Listener for the QTreeWidget Items.
        Shows the clicked analysis graphviz graph.

        Parameters
        ----------
        item : QTreeWidget Item
            The QTreeWidget item clicked.
        col : int
            The QTreeWidget column.

        Returns
        -------
        None.

        """
        
        if item.parent() is None:
            graph_file = self.patient.graph_file(item.get_text(), svg=True)
            if os.path.exists(graph_file):
                self.exec_graph.load(graph_file)
                self.exec_graph.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)

    @staticmethod
    def no_close_event(event):
        """
        Used to prevent the user to close a dialog.

        Parameters
        ----------
        event : TYPE
            The event to ignore.

        Returns
        -------
        None.

        """
        
        event.ignore()

    def toggle_workflow_execution(self, resume: bool = None, resume_freesurfer: bool = None):
        """
        If the workflow is not started, executes it.
        If the workflow is executing, kills it.

        Returns
        -------
        None.

        """
        
        # Workflow not started
        if not self.patient.is_workflow_process_alive():
            workflow_start_ret = self.patient.start_workflow(resume=resume, resume_freesurfer=resume_freesurfer, update_node_callback=self.update_node_list)
            if workflow_start_ret == PatientRet.ExecWfResume:
                msg_box = QMessageBox()
                msg_box.setText(strings.pttab_old_wf_found)
                msg_box.setIcon(QMessageBox.Icon.Question)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg_box.button(QMessageBox.StandardButton.Yes).setText(strings.pttab_old_wf_resume)
                msg_box.button(QMessageBox.StandardButton.No).setText(strings.pttab_old_wf_reset)
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                msg_box.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
                msg_box.closeEvent = self.no_close_event
                ret = msg_box.exec()
                resume = ret == QMessageBox.StandardButton.Yes
                self.toggle_workflow_execution(resume=resume, resume_freesurfer=resume_freesurfer)
            elif workflow_start_ret == PatientRet.ExecWfResumeFreesurfer:
                msg_box = QMessageBox()
                msg_box.setText(strings.pttab_old_fs_found)
                msg_box.setIcon(QMessageBox.Icon.Question)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg_box.button(QMessageBox.StandardButton.Yes).setText(strings.pttab_old_fs_resume)
                msg_box.button(QMessageBox.StandardButton.No).setText(strings.pttab_old_fs_reset)
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                msg_box.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
                msg_box.closeEvent = self.no_close_event
                ret = msg_box.exec()
                resume_freesurfer = ret == QMessageBox.StandardButton.Yes
                self.toggle_workflow_execution(resume=resume, resume_freesurfer=resume_freesurfer)
            elif workflow_start_ret == PatientRet.ExecWfStatusError:
                # Already running, should not be possible
                pass
            else:
                # UI updating
                self.exec_button.setText(strings.EXECBUTTONTEXT_STOP)
                self.setTabEnabled(PatientTab.DATATAB, False)
                self.setTabEnabled(PatientTab.RESULTTAB, False)
                self.wf_type_combo.setEnabled(False)
                self.patient_config_button.setEnabled(False)

        # Workflow executing
        else:
            # Asks for workflow kill confirmation
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_wf_stop)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setDefaultButton(QMessageBox.StandardButton.No)
            msg_box.closeEvent = self.no_close_event
            ret = msg_box.exec()
            
            if ret == QMessageBox.StandardButton.No:
                return

            workflow_stop_ret = self.patient.stop_workflow()
            if workflow_stop_ret == PatientRet.ExecWfStatusError:
                # Not running, should not be possible
                pass
            else:
                # UI updating
                self.remove_running_icon()
                self.exec_button.setText(strings.EXECBUTTONTEXT)
                self.setTabEnabled(PatientTab.DATATAB, True)
                self.reset_workflow(force=True)
                self.enable_tab_if_result_dir()

    def export_results_button_update_state(self):
        try:
            if not DependencyManager.is_slicer(self.global_config):
                self.generate_scene_button.setEnabled(False)
                self.generate_scene_button.setToolTip(strings.pttab_results_button_disabled_tooltip)
            else:
                self.generate_scene_button.setEnabled(True)
                self.generate_scene_button.setToolTip(strings.pttab_results_button_tooltip)
        except:
            pass

    def load_scene_button_update_state(self):
        try:
            if not DependencyManager.is_slicer(self.global_config):
                self.load_scene_button.setEnabled(False)
                self.load_scene_button.setText(strings.pttab_open_results_button + " " + strings.INFOCHAR)
                self.load_scene_button.setToolTip(strings.pttab_results_button_disabled_tooltip)
            elif os.path.exists(self.patient.scene_path()):
                self.load_scene_button.setEnabled(True)
                self.load_scene_button.setToolTip("")
                self.load_scene_button.setText(strings.pttab_open_results_button)
            else:
                self.load_scene_button.setEnabled(False)
                self.load_scene_button.setToolTip(strings.pttab_open_results_button_tooltip)
                self.load_scene_button.setText(strings.pttab_open_results_button + " " + strings.INFOCHAR)
        except:
            pass

    def result_tab_ui(self):
        """
        Generates the Results tab UI.

        Returns
        -------
        None.

        """
        
        result_tab_layout = QGridLayout()
        self.result_tab.setLayout(result_tab_layout)

        self.generate_scene_button = QPushButton(strings.pttab_results_button)
        self.generate_scene_button.clicked.connect(self.generate_scene)
        self.generate_scene_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.generate_scene_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.export_results_button_update_state()
        result_tab_layout.addWidget(self.generate_scene_button, 0, 0)

        horizontal_spacer = QSpacerItem(20, 40, QSizePolicy.Expanding, QSizePolicy.Minimum)
        result_tab_layout.addItem(horizontal_spacer, 0, 1, 1, 1)

        self.load_scene_button = QPushButton(strings.pttab_open_results_button)
        self.load_scene_button.clicked.connect(
            lambda pushed=False, slicer_path=self.global_config.get_slicer_path(), scene_path=self.patient.scene_path(): load_scene(pushed, slicer_path, scene_path)
        )
        self.load_scene_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.load_scene_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.load_scene_button_update_state()
        result_tab_layout.addWidget(self.load_scene_button, 0, 2)

        self.open_results_directory_button = QPushButton(strings.pttab_open_results_directory)
        self.open_results_directory_button.clicked.connect(
            lambda pushed=False, results_dir=self.patient.result_dir(): open_results_directory(pushed, results_dir)
        )
        self.open_results_directory_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.open_results_directory_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        result_tab_layout.addWidget(self.open_results_directory_button, 0, 3)

        self.results_model = QFileSystemModel()
        self.result_tree = QTreeView(parent=self)
        self.result_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_tree.setModel(self.results_model)

        result_tab_layout.addWidget(self.result_tree, 1, 0, 1, 4)

    def generate_scene(self):
        """
        Exports the workflow results into 3D Slicer using a new thread.

        Returns
        -------
        None.

        """
        
        progress = PersistentProgressDialog(strings.pttab_exporting_start, 0, 0, parent=self)
        progress.show()
        self.patient.generate_scene(lambda msg: PatientTab.slicer_thread_signal(msg, progress))

    @staticmethod
    def slicer_thread_signal(msg: str, progress: PersistentProgressDialog):
        """
        Updates the Progress Dialog text to inform the user of the loading status.

        Parameters
        ----------
        msg : str
            The loading text.
        progress : PersistentProgressDialog
            The Progress Dialog.

        Returns
        -------
        None.

        """
        
        if msg == SlicerExportWorker.END_MSG:
            progress.done(1)
        else:
            progress.setLabelText(strings.pttab_exporting_prefix + msg)

    def input_check_update(self, data_input: DataInputList, state: PatientRet, dicom_src_work: DicomSearchWorker = None):
        if data_input not in self.input_report:
            return
        if state == PatientRet.DataInputWarningNoDicom:
            self.set_error(data_input, strings.pttab_no_dicom_error + dicom_src_work.dicom_dir)
        elif state == PatientRet.DataInputWarningMultiPt:
            self.set_warn(data_input, strings.pttab_multi_pt_error + dicom_src_work.dicom_dir)
        elif state == PatientRet.DataInputWarningMultiExam:
            self.set_warn(data_input, strings.pttab_multi_exam_error + dicom_src_work.dicom_dir)
        elif state == PatientRet.DataInputWarningMultiSeries:
            self.set_warn(data_input, strings.pttab_multi_series_error + dicom_src_work.dicom_dir)
        elif state == PatientRet.DataInputLoading:
            self.set_loading(data_input)
        elif state == PatientRet.DataInputValid:

            pt_list = dicom_src_work.get_patient_list()
            exam_list = dicom_src_work.get_exam_list(pt_list[0])
            series_list = dicom_src_work.get_series_list(pt_list[0], exam_list[0])

            image_list = dicom_src_work.get_series_files(pt_list[0], exam_list[0], series_list[0])
            ds = pydicom.read_file(image_list[0], force=True)
            mod = ds.Modality

            label = str(ds.PatientName) + "-" + mod + "-" + ds.SeriesDescription + ": " + str(
                len(image_list)) + " images"
            if data_input == DataInputList.VENOUS or data_input == DataInputList.VENOUS2:
                label += ", " + str(dicom_src_work.get_series_nvol(pt_list[0], exam_list[0], series_list[0])) + " "
                if dicom_src_work.get_series_nvol(pt_list[0], exam_list[0], series_list[0]) > 1:
                    label += "phases"
                else:
                    label += "phase"

            self.set_ok(data_input, label)
            self.enable_exec_tab()
            self.check_venous_volumes()

    def load_patient(self):
        """
        Loads the Patient configuration and folder.

        Returns
        -------
        None.

        """

        self.wf_type_combo.setCurrentIndex(self.patient.config.get_patient_workflow_type())
        # Set after patient loading to prevent the onchanged fire on previous line command
        self.wf_type_combo.currentIndexChanged.connect(self.on_wf_type_changed)

        # Scan patient dicom folder
        dicom_scanners, total_files = self.patient.prepare_scan_dicom_folders()

        if total_files > 0:
            progress = PersistentProgressDialog(strings.pttab_pt_loading, 0, 0, parent=self.parent())
            progress.show()
            progress.setMaximum(total_files)
            self.patient.execute_scan_dicom_folders(dicom_scanners, self.input_check_update, progress.increase_value)

        # Update UI after loading dicom
        self.setTabEnabled(PatientTab.DATATAB, True)
        self.setCurrentWidget(self.data_tab)

        self.clear_scan_result()
        self.reset_workflow()

        self.enable_tab_if_result_dir()

    def enable_tab_if_result_dir(self):
        """
        Enables Results tab, if any.

        Returns
        -------
        None.

        """
        scene_dir = self.patient.result_dir()
        
        if os.path.exists(scene_dir):
            self.setTabEnabled(PatientTab.RESULTTAB, True)
            self.results_model.setRootPath(scene_dir)
            index_root = self.results_model.index(self.results_model.rootPath())
            self.result_tree.setRootIndex(index_root)
            self.result_directory_watcher.addPath(scene_dir)
            self.load_scene_button_update_state()
        else:
            self.setTabEnabled(PatientTab.RESULTTAB, False)
            self.result_directory_watcher.removePaths([scene_dir])

    def clear_import_folder(self, data_input: DataInputList):
        """
        Clears the patient series folder.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to clear.

        Returns
        -------
        None.

        """

        src_path = os.path.join(self.patient.dicom_folder(), str(data_input))

        progress = PersistentProgressDialog(strings.pttab_dicom_clearing + src_path, 0, 0, self)
        progress.show()

        self.patient.clear_import_folder(data_input)

        self.set_error(data_input, strings.pttab_no_dicom_error + src_path)
        self.patient.input_state_list[data_input].loaded = False
        self.patient.input_state_list[data_input].volumes = 0
        self.enable_exec_tab()

        progress.accept()
        
        self.reset_workflow()
        self.check_venous_volumes()

        if data_input == DataInputList.VENOUS and self.patient.input_state_list[DataInputList.VENOUS2].loaded:
            self.clear_import_folder(DataInputList.VENOUS2)

    def check_venous_volumes(self):
        phases = self.patient.input_state_list[DataInputList.VENOUS].volumes + self.patient.input_state_list[DataInputList.VENOUS2].volumes
        if phases == 0:
            self.input_report[DataInputList.VENOUS2][3].setEnabled(False)
        elif phases == 1:
            if self.patient.input_state_list[DataInputList.VENOUS].loaded:
                self.set_warn(DataInputList.VENOUS, "Series has only one phase, load the second phase below", False)
                self.input_report[DataInputList.VENOUS2][3].setEnabled(True)
            if self.patient.input_state_list[DataInputList.VENOUS2].loaded:
                # this should not be possible!
                self.set_warn(DataInputList.VENOUS2, "Series has only one phase, load the second phase above", False)
        elif phases == 2:
            if self.patient.input_state_list[DataInputList.VENOUS].loaded:
                self.set_ok(DataInputList.VENOUS, None)
                self.input_report[DataInputList.VENOUS2][3].setEnabled(False)
            if self.patient.input_state_list[DataInputList.VENOUS2].loaded:
                self.set_ok(DataInputList.VENOUS2, None)
        else:
            # something gone wrong, more than 2 phases!
            if self.patient.input_state_list[DataInputList.VENOUS].loaded:
                self.set_warn(DataInputList.VENOUS, "Too many venous phases loaded, delete some!", False)
                self.input_report[DataInputList.VENOUS2][3].setEnabled(True)
            if self.patient.input_state_list[DataInputList.VENOUS2].loaded:
                self.set_warn(DataInputList.VENOUS2, "Too many venous phases loaded, delete some!", False)

    def exec_button_setEnabled(self, enabled):
        if enabled:
            self.exec_button.setEnabled(True)
            self.exec_button.setToolTip("")
            self.exec_button.setText(strings.EXECBUTTONTEXT)
        else:
            self.exec_button.setEnabled(False)
            self.exec_button.setToolTip(strings.EXECBUTTONTEXT_disabled_tooltip)
            self.exec_button.setText(strings.EXECBUTTONTEXT + "  " + strings.INFOCHAR)

    def reset_workflow(self, force: bool = False):
        """
        Set the workflow var to None.
        Resets the UI.
        Works only if the worklow is not in execution or if force var is True.

        Parameters
        ----------
        force : bool, optional
            Force the usage of this function during workflow execution. The default is False.

        Returns
        -------
        None.

        """

        if self.patient.reset_workflow(force):
            self.node_list_treeWidget.clear()
            self.exec_graph.load(self.main_window.VOID_SVG_FILE)
            self.exec_button_setEnabled(False)
            self.node_button.setEnabled(True)
            self.wf_type_combo.setEnabled(True)
            self.patient_config_button.setEnabled(True)

    def result_directory_changed(self):
        self.enable_tab_if_result_dir()

    def show_scan_result(self, dicom_src_work: DicomSearchWorker):
        """
        Updates importable series list using DICOM Search Worker results.

        Parameters
        ----------
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.

        Returns
        -------
        None.

        """
        
        folder_path = dicom_src_work.dicom_dir
        self.scan_directory_watcher.addPath(folder_path)
        pt_list = dicom_src_work.get_patient_list()

        if len(pt_list) == 0:
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_no_dicom_error + folder_path)
            msg_box.exec()
            return
        
        if len(pt_list) > 1:
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_multi_pt_error + folder_path)
            msg_box.exec()
            return
        
        exam_list = dicom_src_work.get_exam_list(pt_list[0])
        
        for exam in exam_list:
            series_list = dicom_src_work.get_series_list(pt_list[0], exam)
            for series in series_list:
                image_list = dicom_src_work.get_series_files(pt_list[0], exam, series)
                ds = pydicom.read_file(image_list[0], force=True)
                
                # Excludes series with less than 10 images unless they are siemens mosaics series
                if len(image_list) < 10 and hasattr(ds, 'ImageType') and "MOSAIC" not in ds.ImageType:
                    continue

                mod = ds.Modality
                vols = dicom_src_work.get_series_nvol(pt_list[0], exam, series)

                label = str(ds.PatientName) + "-" + mod + "-" + ds.SeriesDescription + ": " + str(
                        len(image_list)) + " images, " + str(vols) + " "
                if dicom_src_work.get_series_nvol(pt_list[0], exam, series) > 1:
                    label += "volumes"
                else:
                    label += "volume"

                self.dicom_scan_series_list.append(
                    [label, image_list, mod, vols])
                del image_list

        for series in self.dicom_scan_series_list:
            self.importable_series_list.addItem(series[0])

    def clear_scan_result(self):
        self.importable_series_list.clear()
        self.dicom_scan_series_list = None
        if len(self.scan_directory_watcher.directories()) > 0:
            self.scan_directory_watcher.removePaths(self.scan_directory_watcher.directories())

    def update_input_report(self, data_input: DataInputList, icon: str, tooltip: str, import_enable: bool, clear_enable: bool, text: str = None):
        """
        Generic update function for series labels.

        Parameters
        ----------
        data_input: DataInputList
            The series label.
        icon: str
            The icon file to set near the label
        tooltip: str
            Mouse over tooltip:
        import_enable: bool
            The enable status of the import series button
        clear_enable: bool
            The enable status of the clear series button
        text: str
            The text to show under the label, if not None. Default is None
        """
        self.input_report[data_input][0].load(icon)
        self.input_report[data_input][0].setFixedSize(25, 25)
        self.input_report[data_input][0].setToolTip(tooltip)
        self.input_report[data_input][3].setEnabled(import_enable)
        self.input_report[data_input][4].setEnabled(clear_enable)
        if text is not None:
            self.input_report[data_input][2].setText(text)

    def set_warn(self, data_input: DataInputList, tooltip: str, clear_text: bool = True):
        """
        Set a warning message and icon near a series label.

        Parameters
        ----------
        data_input : DataInputList
            The series label.
        tooltip : str
            The warning message.
        clear_text : bool
            If True delete the label text

        Returns
        -------
        None.

        """
        text = None
        if clear_text:
            text = ""

        self.update_input_report(
            data_input=data_input,
            icon=self.main_window.WARNING_ICON_FILE,
            tooltip=tooltip,
            import_enable=True,
            clear_enable=False,
            text=text
        )

    def set_error(self, data_input: DataInputList, tooltip: str):
        """
        Set an error message and icon near a series label.

        Parameters
        ----------
        data_input : DataInputList
            The series label.
        tooltip : str
            The error message.
        """

        self.update_input_report(
            data_input=data_input,
            icon=self.main_window.ERROR_ICON_FILE,
            tooltip=tooltip,
            import_enable=True,
            clear_enable=False,
            text=""
        )

    def set_ok(self, data_input: DataInputList, text: str):
        """
        Set a success message and icon near a series label.

        Parameters
        ----------
        data_input : DataInputList
            The series label.
        text : str
            The success message. If string is None keep the current text
        """
        self.update_input_report(
            data_input=data_input,
            icon=self.main_window.OK_ICON_FILE,
            tooltip="",
            import_enable=False,
            clear_enable=True,
            text=text,
        )

    def set_loading(self, data_input: DataInputList):
        """
        Set a loading message and icon near a series label.

        Parameters
        ----------
        data_input : DataInputList
            The series label.
        """
        self.update_input_report(
            data_input=data_input,
            icon=self.main_window.LOADING_MOVIE_FILE,
            tooltip="",
            import_enable=False,
            clear_enable=False,
            text=None,
        )

    def enable_exec_tab(self):
        """
        Enables the Execute Workflow tab into the UI.

        Returns
        -------
        None.

        """
        
        enable = self.patient.can_generate_workflow()
        self.setTabEnabled(PatientTab.EXECTAB, enable)

    def setTabEnabled(self, index, enabled):
        if index == PatientTab.EXECTAB and not enabled:
            if not self.patient.dependency_manager.is_fsl() or not self.patient.dependency_manager.is_dcm2niix():
                self.setTabToolTip(index, strings.pttab_tabtooltip_exec_disabled_dependency)
            else:
                self.setTabToolTip(index, strings.pttab_tabtooltip_exec_disabled_series)
        elif index == PatientTab.RESULTTAB and not enabled:
            self.setTabToolTip(index, strings.pttab_tabtooltip_result_disabled)
        elif index == PatientTab.DATATAB and not enabled:
            self.setTabToolTip(index, strings.pttab_tabtooltip_data_disabled)
        else:
            self.setTabToolTip(index, "")
        super().setTabEnabled(index, enabled)

    def setTabToolTip(self, index, tip):
        super().setTabToolTip(index, tip)
        if tip == "" and self.tabText(index).endswith(strings.INFOCHAR):
            self.setTabText(index, self.tabText(index).replace(" "+strings.INFOCHAR, ""))
        elif tip != "" and not self.tabText(index).endswith(strings.INFOCHAR):
            self.setTabText(index, self.tabText(index) + " " + strings.INFOCHAR)