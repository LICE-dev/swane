import os
from functools import partial
from datetime import datetime
from PySide6.QtCore import Qt, QThreadPool, QFileSystemWatcher
from PySide6.QtGui import QFont
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QTabWidget, QWidget, QGridLayout, QLabel, QHeaderView,
                               QPushButton, QSizePolicy, QHBoxLayout, QSpacerItem,
                               QGroupBox, QVBoxLayout, QMessageBox, QListWidget,
                               QFileDialog, QTreeWidget, QErrorMessage, QFileSystemModel,
                               QTreeView, QComboBox)

from swane import strings
from swane.utils.DicomTree import DicomTree
from swane.workers.SlicerExportWorker import SlicerExportWorker
from swane.workers.SlicerViewerWorker import SlicerViewerWorker
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
from swane.utils.Subject import Subject, SubjectRet
from swane.workers.open_results_directory import open_results_directory


class SubjectTab(QTabWidget):
    """
    Custom implementation of PySide QTabWidget to define a subject tab widget.

    """
    
    DATATAB = 0
    EXECTAB = 1
    RESULTTAB = 2

    def __init__(self, global_config: ConfigManager, subject: Subject, main_window, parent=None):
        super(SubjectTab, self).__init__(parent)
        self.global_config = global_config
        self.subject = subject
        self.main_window = main_window

        self.data_tab = QWidget()
        self.exec_tab = QWidget()
        self.result_tab = QWidget()

        self.addTab(self.data_tab, strings.subj_tab_data_tab_name)
        self.addTab(self.exec_tab, strings.subj_tab_wf_tab_name)
        self.addTab(self.result_tab, strings.subj_tab_results_tab_name)

        self.directory_watcher = QFileSystemWatcher()
        self.directory_watcher.directoryChanged.connect(self.reset_workflow)

        self.scan_directory_watcher = QFileSystemWatcher()
        self.scan_directory_watcher.directoryChanged.connect(self.clear_scan_result)

        self.result_directory_watcher = QFileSystemWatcher()
        self.result_directory_watcher.directoryChanged.connect(self.enable_tab_if_result_dir)
        self.result_directory_watcher.addPath(self.subject.folder)

        self.workflow_process = None
        self.node_list = None
        self.input_report = {}
        self.dicom_scan_series_list = []
        self.importable_series_list = QListWidget()
        self.workflow_type_combo = None
        self.generate_workflow_button = None
        self.node_list_treeWidget = None
        self.subject_config_button = None
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

        self.setTabEnabled(SubjectTab.EXECTAB, False)
        self.setTabEnabled(SubjectTab.RESULTTAB, False)

    def update_node_list(self, wf_report: WorkflowReport):
        """
        Searches for the node linked to the wf_report arg.
        Uses the wf_report arg to update the node status.

        Parameters
        ----------
        wf_report : WorkflowReport
            Workflow Monitor Worker message to parse.

        Returns
        -------
        None.

        """
        
        if wf_report.signal_type == WorkflowSignals.WORKFLOW_STOP:
            self.enable_tab_if_result_dir(on_workflow_running=True)
            errors = False
            for key in self.node_list.keys():
                self.node_list[key].node_holder.setExpanded(False)
                if not self.node_list[key].node_holder.completed:
                    errors = True
                    for subkey in self.node_list[key].node_list.keys():
                        if self.node_list[key].node_list[subkey].node_holder.art == self.main_window.ERROR_ICON_FILE:
                            self.node_list[key].node_holder.set_art(self.main_window.ERROR_ICON_FILE)
                            break

            self.setTabEnabled(SubjectTab.DATATAB, True)

            self.exec_button_set_enabled(False)

            if errors:
                self.generate_workflow_button.setEnabled(True)
                self.subject.workflow = None
                self.exec_button.setText(strings.subj_tab_wf_executed_with_error)
                self.exec_button.setToolTip("")
            else:
                self.exec_button.setText(strings.subj_tab_wf_executed)
                self.exec_button.setToolTip("")


            
            return
        elif wf_report.signal_type == WorkflowSignals.INVALID_SIGNAL:
            # Invalid signal sent from WF to UI, code error intercept
            try:
                self.workflow_process.stop_event.set()
            except:
                pass
            msg_box = QMessageBox()
            msg_box.setText(strings.subj_tab_wf_invalid_signal)
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
            # Mail manager initialization
            mail_manager = self.global_config.get_mail_manager()
            if mail_manager is not None:
                try:
                    mail_manager.send_report(f"{self.subject.name} - {wf_report.workflow_name} - {wf_report.node_name} FAILED at {datetime.now()}")
                except:
                    pass

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
                # Mail manager initialization
                mail_manager = self.global_config.get_mail_manager()
                if mail_manager is not None:
                    try:
                        mail_manager.send_report(f"{self.subject.name} - {wf_report.workflow_name} COMPLETED at {datetime.now()}")
                    except:
                        pass


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

        for data_input in self.subject.input_state_list:
            self.input_report[data_input] = [QSvgWidget(self),
                                             QLabel(data_input.value.label),
                                             QLabel(""),
                                             QPushButton(strings.subj_tab_import_button),
                                             QPushButton(strings.subj_tab_clear_button),
                                             None]
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

        scan_dicom_folder_button = QPushButton(strings.subj_tab_scan_dicom_button)
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
            msg_box.setText(strings.subj_tab_selected_series_error)
            msg_box.exec()
            return

        copy_list = self.dicom_scan_series_list[self.importable_series_list.currentRow()][1]
        vols = self.dicom_scan_series_list[self.importable_series_list.currentRow()][3]
        found_mod = self.dicom_scan_series_list[self.importable_series_list.currentRow()][2].upper()

        progress = PersistentProgressDialog(strings.subj_tab_dicom_copy, 0, len(copy_list) + 1, self)
        self.set_loading(data_input)

        # Copy files and check for return
        import_ret = self.subject.dicom_import_to_folder(data_input=data_input,
                                                         copy_list=copy_list,
                                                         vols=vols,
                                                         mod=found_mod,
                                                         force_modality=force_mod,
                                                         progress_callback=progress.increase_value
                                                         )
        if import_ret != SubjectRet.DataImportCompleted:
            if import_ret == SubjectRet.DataImportErrorVolumesMax:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_wrong_max_vols_check_msg % (vols, data_input.value.max_volumes))
                msg_box.exec()
            elif import_ret == SubjectRet.DataInputNonEmpty:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_import_folder_not_empy)
                msg_box.exec()
            elif import_ret == SubjectRet.DataImportErrorVolumesMin:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_wrong_min_vols_check_msg % (vols, data_input.value.min_volumes))
                msg_box.exec()
            elif import_ret == SubjectRet.DataImportErrorCopy:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_import_copy_error_msg)
                msg_box.exec()
            elif import_ret == SubjectRet.DataImportErrorModality:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_wrong_type_check_msg % (found_mod, data_input.value.image_modality.value))
                msg_box.setInformativeText(strings.subj_tab_wrong_type_check)
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
        progress.setLabelText(strings.subj_tab_dicom_check)

        self.subject.check_input_folder(data_input, status_callback=self.input_check_update, progress_callback=progress.increase_value)
        self.reset_workflow()

    def scan_dicom_folder(self):
        """
        Opens a folder dialog window to select the DICOM files folder to import.
        Scans the folder in a new thread.

        Returns
        -------
        None.

        """
        
        folder_path = QFileDialog.getExistingDirectory(self, strings.subj_tab_select_dicom_folder)
        
        if not os.path.exists(folder_path):
            return

        dicom_src_work = DicomSearchWorker(folder_path)
        dicom_src_work.load_dir()

        if dicom_src_work.get_files_len() > 0:
            self.clear_scan_result()
            self.dicom_scan_series_list = []
            progress = PersistentProgressDialog(strings.subj_tab_dicom_scan, 0, 0, parent=self.parent())
            progress.show()
            progress.setMaximum(dicom_src_work.get_files_len())
            dicom_src_work.signal.sig_loop.connect(lambda i: progress.increase_value(i))
            dicom_src_work.signal.sig_finish.connect(self.show_scan_result)
            QThreadPool.globalInstance().start(dicom_src_work)

        else:
            msg_box = QMessageBox()
            msg_box.setText(strings.subj_tab_no_dicom_error + folder_path)
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
        self.workflow_type_combo = QComboBox(self)

        for row in WORKFLOW_TYPES:
            self.workflow_type_combo.addItem(row.value, userData=row.name)

        layout.addWidget(self.workflow_type_combo, 0, 0)

        self.generate_workflow_button = QPushButton(strings.GENBUTTONTEXT)
        self.generate_workflow_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.generate_workflow_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.generate_workflow_button.clicked.connect(self.generate_workflow)

        layout.addWidget(self.generate_workflow_button, 1, 0)

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
        self.subject_config_button = QPushButton(strings.SUBJCONFIGBUTTONTEXT)
        self.subject_config_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.subject_config_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.subject_config_button.clicked.connect(self.edit_subject_config)
        layout.addWidget(self.subject_config_button, 0, 1)

        self.exec_button = QPushButton(strings.EXECBUTTONTEXT)
        self.exec_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.exec_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.exec_button.clicked.connect(partial(self.toggle_workflow_execution, None, None))
        self.exec_button_set_enabled(False)

        layout.addWidget(self.exec_button, 1, 1)
        self.exec_graph = QSvgWidget()
        layout.addWidget(self.exec_graph, 2, 1)

        self.exec_tab.setLayout(layout)

    def edit_subject_config(self):
        """
        Opens the subject Preference Window.

        Returns
        -------
        None.

        """

        preference_window = PreferencesWindow(self.subject.config, self.subject.dependency_manager, True, self)
        ret = preference_window.exec()
        if ret != 0:
            self.reset_workflow()
        if ret == -1:
            self.subject.config.reset_to_defaults()
            self.edit_subject_config()

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

        new_workflow_type = self.workflow_type_combo.itemData(index)
        self.subject.config.set_workflow_option(WORKFLOW_TYPES[new_workflow_type])
        self.subject.config.save()
        self.reset_workflow()

    def generate_workflow(self):
        """
        Generates and populates the Main Workflow.
        Shows the node list into the UI.
        Generates the graphviz analysis graphs on a new thread.

        Returns
        -------
        None.

        """
        
        generate_workflow_return = self.subject.generate_workflow()
        
        if generate_workflow_return == SubjectRet.GenWfMissingRequisites:
            error_dialog = QErrorMessage(parent=self)
            error_dialog.showMessage(strings.subj_tab_missing_fsl_error)
            return
        elif generate_workflow_return == SubjectRet.GenWfError:
            error_dialog = QErrorMessage(parent=self)
            error_dialog.showMessage(strings.subj_tab_wf_gen_error)
            return
        
        self.node_list_treeWidget.clear()
        self.node_list = self.subject.workflow.get_node_array()
        
        # Graphviz analysis graphs drawing
        for node in self.node_list.keys():
            self.node_list[node].node_holder = CustomTreeWidgetItem(self.node_list_treeWidget, self.node_list_treeWidget, self.node_list[node].long_name)
            if len(self.node_list[node].node_list.keys()) > 0:                    
                for sub_node in self.node_list[node].node_list.keys():
                    self.node_list[node].node_list[sub_node].node_holder = CustomTreeWidgetItem(self.node_list[node].node_holder, self.node_list_treeWidget, self.node_list[node].node_list[sub_node].long_name)
        
        # UI updating
        self.exec_button_set_enabled(True)
        self.generate_workflow_button.setEnabled(False)

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
            graph_file = self.subject.graph_file(item.get_text())
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
        if not self.subject.is_workflow_process_alive():
            workflow_start_ret = self.subject.start_workflow(resume=resume, resume_freesurfer=resume_freesurfer, update_node_callback=self.update_node_list)
            if workflow_start_ret == SubjectRet.ExecWfResume:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_old_wf_found)
                msg_box.setIcon(QMessageBox.Icon.Question)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg_box.button(QMessageBox.StandardButton.Yes).setText(strings.subj_tab_old_wf_resume)
                msg_box.button(QMessageBox.StandardButton.No).setText(strings.subj_tab_old_wf_reset)
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                msg_box.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
                msg_box.closeEvent = self.no_close_event
                ret = msg_box.exec()
                resume = ret == QMessageBox.StandardButton.Yes
                self.toggle_workflow_execution(resume=resume, resume_freesurfer=resume_freesurfer)
            elif workflow_start_ret == SubjectRet.ExecWfResumeFreesurfer:
                msg_box = QMessageBox()
                msg_box.setText(strings.subj_tab_old_fs_found)
                msg_box.setIcon(QMessageBox.Icon.Question)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg_box.button(QMessageBox.StandardButton.Yes).setText(strings.subj_tab_old_fs_resume)
                msg_box.button(QMessageBox.StandardButton.No).setText(strings.subj_tab_old_fs_reset)
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                msg_box.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint)
                msg_box.closeEvent = self.no_close_event
                ret = msg_box.exec()
                resume_freesurfer = ret == QMessageBox.StandardButton.Yes
                self.toggle_workflow_execution(resume=resume, resume_freesurfer=resume_freesurfer)
            elif workflow_start_ret == SubjectRet.ExecWfStatusError:
                # Already running, should not be possible
                pass
            else:
                # UI updating
                self.exec_button.setText(strings.EXECBUTTONTEXT_STOP)
                self.setTabEnabled(SubjectTab.DATATAB, False)
                self.setTabEnabled(SubjectTab.RESULTTAB, False)
                self.workflow_type_combo.setEnabled(False)
                self.subject_config_button.setEnabled(False)

        # Workflow executing
        else:
            # Asks for workflow kill confirmation
            msg_box = QMessageBox()
            msg_box.setText(strings.subj_tab_wf_stop)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setDefaultButton(QMessageBox.StandardButton.No)
            msg_box.closeEvent = self.no_close_event
            ret = msg_box.exec()
            
            if ret == QMessageBox.StandardButton.No:
                return

            workflow_stop_ret = self.subject.stop_workflow()
            if workflow_stop_ret == SubjectRet.ExecWfStatusError:
                # Not running, should not be possible
                pass
            else:
                # UI updating
                self.remove_running_icon()
                self.exec_button.setText(strings.EXECBUTTONTEXT)
                self.setTabEnabled(SubjectTab.DATATAB, True)
                self.reset_workflow(force=True)
                self.enable_tab_if_result_dir()

    def export_results_button_update_state(self):
        """
        Enable the export results button if Slicer is found on system
        """
        try:
            if not DependencyManager.is_slicer(self.global_config):
                self.generate_scene_button.setEnabled(False)
                self.generate_scene_button.setToolTip(strings.subj_tab_generate_scene_button_disabled_tooltip)
            else:
                self.generate_scene_button.setEnabled(True)
                self.generate_scene_button.setToolTip(strings.subj_tab_generate_scene_button_tooltip)
        except:
            pass

    def load_scene_button_update_state(self):
        """
        Enable the load scene button if a scene file is present, otherwise disable it
        """
        try:
            if not DependencyManager.is_slicer(self.global_config):
                self.load_scene_button.setEnabled(False)
                self.load_scene_button.setText(strings.subj_tab_load_scene_button + " " + strings.INFOCHAR)
                self.load_scene_button.setToolTip(strings.subj_tab_generate_scene_button_disabled_tooltip)
            elif os.path.exists(self.subject.scene_path()):
                self.load_scene_button.setEnabled(True)
                self.load_scene_button.setToolTip("")
                self.load_scene_button.setText(strings.subj_tab_load_scene_button)
            else:
                self.load_scene_button.setEnabled(False)
                self.load_scene_button.setToolTip(strings.subj_tab_load_scene_button_tooltip)
                self.load_scene_button.setText(strings.subj_tab_load_scene_button + " " + strings.INFOCHAR)
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

        self.generate_scene_button = QPushButton(strings.subj_tab_generate_scene_button)
        self.generate_scene_button.clicked.connect(self.generate_scene)
        self.generate_scene_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.generate_scene_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.export_results_button_update_state()
        result_tab_layout.addWidget(self.generate_scene_button, 0, 0)

        horizontal_spacer = QSpacerItem(20, 40, QSizePolicy.Expanding, QSizePolicy.Minimum)
        result_tab_layout.addItem(horizontal_spacer, 0, 1, 1, 1)

        self.load_scene_button = QPushButton(strings.subj_tab_load_scene_button)
        self.load_scene_button.clicked.connect(self.load_scene)
        self.load_scene_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        self.load_scene_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.load_scene_button_update_state()
        result_tab_layout.addWidget(self.load_scene_button, 0, 2)

        self.open_results_directory_button = QPushButton(strings.subj_tab_open_results_directory)
        self.open_results_directory_button.clicked.connect(
            lambda pushed=False, results_dir=self.subject.result_dir(): open_results_directory(pushed, results_dir)
        )
        self.open_results_directory_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.open_results_directory_button.setFixedHeight(self.main_window.NON_UNICODE_BUTTON_HEIGHT)
        result_tab_layout.addWidget(self.open_results_directory_button, 0, 3)

        self.results_model = QFileSystemModel()
        self.result_tree = QTreeView(parent=self)
        self.result_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_tree.setModel(self.results_model)

        result_tab_layout.addWidget(self.result_tree, 1, 0, 1, 4)

    def generate_scene(self) -> PersistentProgressDialog:
        """
        Exports the workflow results into 3D Slicer using a new thread.

        Returns
        -------
        The progress dialog shown.

        """
        
        progress = PersistentProgressDialog(strings.subj_tab_exporting_start, 0, 0, parent=self)
        progress.show()
        self.subject.generate_scene(lambda msg: SubjectTab.slicer_thread_signal(msg, progress))
        return progress

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
            progress.setLabelText(strings.subj_tab_exporting_prefix + msg)

    def input_check_update(self, data_input: DataInputList, state: SubjectRet, dicom_src_worker: DicomSearchWorker = None):
        """
        Function used as callback after subject dicom folder check

        Parameters
        ----------
        data_input: DataInputList
            The data input checked
        state: SubjectRet
            The return code of the scan
        dicom_src_worker: DicomSearchWorker, optional
            The dicom scanner calling the function. Default is None
        """
        if data_input not in self.input_report:
            return
        if state == SubjectRet.DataInputWarningNoDicom:
            self.set_error(data_input, strings.subj_tab_no_dicom_error + dicom_src_worker.dicom_dir)
        elif state == SubjectRet.DataInputWarningMultiSubj:
            self.set_warn(data_input, strings.subj_tab_multi_subj_error + dicom_src_worker.dicom_dir)
        elif state == SubjectRet.DataInputWarningMultiStudy:
            self.set_warn(data_input, strings.subj_tab_multi_exam_error + dicom_src_worker.dicom_dir)
        elif state == SubjectRet.DataInputWarningMultiSeries:
            self.set_warn(data_input, strings.subj_tab_multi_series_error + dicom_src_worker.dicom_dir)
        elif state == SubjectRet.DataInputLoading:
            self.set_loading(data_input)
        elif state == SubjectRet.DataInputValid:

            subject_list = dicom_src_worker.tree.get_subject_list()
            exam_list = dicom_src_worker.tree.get_studies_list(subject_list[0])
            series_list = dicom_src_worker.tree.get_series_list(subject_list[0], exam_list[0])
            series = dicom_src_worker.tree.get_series(subject_list[0], exam_list[0], series_list[0])
            subject_name = dicom_src_worker.tree.dicom_subjects[subject_list[0]].subject_name
            series_description = series.description
            vols = series.volumes
            mod = series.modality
            frames = series.frames

            label = SubjectTab.label_from_dicom(frames, subject_name, mod, series_description, vols)

            self.set_ok(data_input, label)
            self.enable_exec_tab()
            self.check_venous_volumes()

    def load_subject(self):
        """
        Loads the subject configuration and folder.

        Returns
        -------
        None.

        """

        index = self.workflow_type_combo.findData(self.subject.config.get_subject_workflow_type().name)
        self.workflow_type_combo.setCurrentIndex(index)
        # Set after subject loading to prevent the onchanged fire on previous line command
        self.workflow_type_combo.currentIndexChanged.connect(self.on_wf_type_changed)

        # Scan subject dicom folder
        dicom_scanners, total_files = self.subject.prepare_scan_dicom_folders()

        if total_files > 0:
            progress = PersistentProgressDialog(strings.subj_tab_subj_loading, 0, 0, parent=self.parent())
            progress.show()
            progress.setMaximum(total_files)
            self.subject.execute_scan_dicom_folders(dicom_scanners, status_callback=self.input_check_update,
                                                    progress_callback=progress.increase_value)

        # Update UI after loading dicom
        self.setTabEnabled(SubjectTab.DATATAB, True)
        self.setCurrentWidget(self.data_tab)

        self.clear_scan_result()
        self.reset_workflow()

        self.enable_tab_if_result_dir()

    def enable_tab_if_result_dir(self, changed_path: str = "", on_workflow_running: bool = False):
        """
        Enables Results tab, if any.

        Parameters
        _______
        changed_path: str
            The changed directory, passed if called by watcher
        on_workflow_running: bool
            If True, updte states even if workflow is running. Default is False.

        Returns
        -------
        None.

        """
        scene_dir = self.subject.result_dir()

        if self.subject.is_workflow_process_alive() and not on_workflow_running:
            return
        
        if os.path.exists(scene_dir):
            self.setTabEnabled(SubjectTab.RESULTTAB, True)
            self.results_model.setRootPath(scene_dir)
            index_root = self.results_model.index(self.results_model.rootPath())
            self.result_tree.setRootIndex(index_root)
            self.result_directory_watcher.addPath(scene_dir)
            self.load_scene_button_update_state()
        else:
            self.setTabEnabled(SubjectTab.RESULTTAB, False)
            self.result_directory_watcher.removePaths([scene_dir])

    def clear_import_folder(self, data_input: DataInputList):
        """
        Clears the subject series folder.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to clear.

        Returns
        -------
        None.

        """

        src_path = self.subject.dicom_folder(data_input)

        progress = PersistentProgressDialog(strings.subj_tab_dicom_clearing + src_path, 0, 0, self)
        progress.show()

        self.subject.clear_import_folder(data_input)

        self.set_error(data_input, strings.subj_tab_no_dicom_error + src_path)
        self.enable_exec_tab()

        progress.accept()

        self.reset_workflow()
        self.check_venous_volumes()

        if data_input == DataInputList.VENOUS and self.subject.input_state_list[DataInputList.VENOUS2].loaded:
            self.clear_import_folder(DataInputList.VENOUS2)

    def check_venous_volumes(self):
        """
        Display informative warnings in venous and venous2 data input rows to help user in data loading
        """
        phases = self.subject.input_state_list[DataInputList.VENOUS].volumes + self.subject.input_state_list[DataInputList.VENOUS2].volumes
        if phases == 0:
            self.input_report[DataInputList.VENOUS2][3].setEnabled(False)
        elif phases == 1:
            if self.subject.input_state_list[DataInputList.VENOUS].loaded:
                self.set_warn(DataInputList.VENOUS, "Series has only one phase, load the second phase below", False)
                self.input_report[DataInputList.VENOUS2][3].setEnabled(True)
            if self.subject.input_state_list[DataInputList.VENOUS2].loaded:
                # this should not be possible!
                self.set_warn(DataInputList.VENOUS2, "Series has only one phase, load the second phase above", False)
        elif phases == 2:
            if self.subject.input_state_list[DataInputList.VENOUS].loaded:
                self.set_ok(DataInputList.VENOUS, None)
                self.input_report[DataInputList.VENOUS2][3].setEnabled(False)
            if self.subject.input_state_list[DataInputList.VENOUS2].loaded:
                self.set_ok(DataInputList.VENOUS2, None)
        else:
            # something gone wrong, more than 2 phases!
            if self.subject.input_state_list[DataInputList.VENOUS].loaded:
                self.set_warn(DataInputList.VENOUS, "Too many venous phases loaded, delete some!", False)
                self.input_report[DataInputList.VENOUS2][3].setEnabled(True)
            if self.subject.input_state_list[DataInputList.VENOUS2].loaded:
                self.set_warn(DataInputList.VENOUS2, "Too many venous phases loaded, delete some!", False)

    def exec_button_set_enabled(self, enabled: bool):
        """
        Change the status and the tooltip of the exec workflow button.

        Parameters
        ----------
        enabled : bool
            The new status of the button
        """
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

        if self.subject.reset_workflow(force):
            self.node_list_treeWidget.clear()
            self.exec_graph.load(self.main_window.VOID_SVG_FILE)
            self.exec_button_set_enabled(False)
            self.generate_workflow_button.setEnabled(True)
            self.workflow_type_combo.setEnabled(True)
            self.subject_config_button.setEnabled(True)

    @staticmethod
    def label_from_dicom(frames: int, subject_name: str, mod: str, series_description: str, vols: int) -> str:
        """
        Compose dicom scan result into a readable label

        Parameters
        ----------
        image_list : list[str]
            The list of file found
        subject_name: str
            The subject name found
        mod: str
            The image modality found
        series_description: str
            The series description found
        vols: int
            The volumes count found in the series

        Returns
        -------
        A string containing the label text

        """
        try:
            # TODO: show correct image number for multiframe dicom
            label = subject_name + "-" + mod + "-" + series_description + ": " + str(
                frames) + " images, " + str(vols) + " "
            if vols > 1:
                label += "volumes"
            else:
                label += "volume"
            return label
        except:
            return ""

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
        subject_list = dicom_src_work.tree.get_subject_list()

        if len(subject_list) == 0:
            msg_box = QMessageBox()
            msg_box.setText(strings.subj_tab_no_dicom_error + folder_path)
            msg_box.exec()
            return
        
        if len(subject_list) > 1:
            msg_box = QMessageBox()
            msg_box.setText(strings.subj_tab_multi_subj_error + folder_path)
            msg_box.exec()
            return
        
        studies_list = dicom_src_work.tree.get_studies_list(subject_list[0])
        
        for study in studies_list:
            series_list = dicom_src_work.tree.get_series_list(subject_list[0], study)
            for series in series_list:
                dicom_series = dicom_src_work.tree.get_series(subject_list[0], study, series)
                frames = dicom_series.frames
                if frames == 0:
                    continue
                subject_name = dicom_src_work.tree.dicom_subjects[subject_list[0]].subject_name
                mod = dicom_series.modality
                series_description = dicom_series.description
                vols = dicom_series.volumes
                label = SubjectTab.label_from_dicom(frames, subject_name, mod, series_description, vols)
                self.dicom_scan_series_list.append(
                    [label, dicom_series.dicom_locs, mod, vols])

        for series in self.dicom_scan_series_list:
            self.importable_series_list.addItem(series[0])

    def clear_scan_result(self):
        """
        Clear the content of the scan result list
        """
        self.importable_series_list.clear()
        self.dicom_scan_series_list = None
        if len(self.scan_directory_watcher.directories()) > 0:
            self.scan_directory_watcher.removePaths(self.scan_directory_watcher.directories())

    def is_data_loading(self) -> bool:
        """
        Returns
            True if any data folder is being scanned
        """

        for row in self.input_report.values():
            if row[5] == self.main_window.LOADING_MOVIE_FILE:
                return True
        return False

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
        self.input_report[data_input][5] = icon
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
            import_enable=False,
            clear_enable=True,
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
        
        enable = self.subject.can_generate_workflow()
        self.setTabEnabled(SubjectTab.EXECTAB, enable)

    def load_scene(self):
        """
            Visualize the workflow results into 3D Slicer.
        """

        slicer_open_thread = SlicerViewerWorker(self.global_config.get_slicer_path(), self.subject.scene_path())
        QThreadPool.globalInstance().start(slicer_open_thread)

    def setTabEnabled(self, index: int, enabled: bool):
        """
        Changes the status of a tab and set an informative tooltip

        Parameters
        -------
        index: int
            The tab index
        enabled: bool
            The new tab status
        """
        if index == SubjectTab.EXECTAB and not enabled:
            if not self.subject.dependency_manager.is_fsl() or not self.subject.dependency_manager.is_dcm2niix():
                self.setTabToolTip(index, strings.subj_tab_tabtooltip_exec_disabled_dependency)
            else:
                self.setTabToolTip(index, strings.subj_tab_tabtooltip_exec_disabled_series)
        elif index == SubjectTab.RESULTTAB and not enabled:
            self.setTabToolTip(index, strings.subj_tab_tabtooltip_result_disabled)
        elif index == SubjectTab.DATATAB and not enabled:
            self.setTabToolTip(index, strings.subj_tab_tabtooltip_data_disabled)
        else:
            self.setTabToolTip(index, "")
        super().setTabEnabled(index, enabled)

    def setTabToolTip(self, index: int, tooltip: str):
        """
        Changes the tooltip of a tab

        Parameters
        -------
        index: int
            The tab index
        tooltip: str
            The tooltip to show
        """
        super().setTabToolTip(index, tooltip)
        if tooltip == "" and self.tabText(index).endswith(strings.INFOCHAR):
            self.setTabText(index, self.tabText(index).replace(" "+strings.INFOCHAR, ""))
        elif tooltip != "" and not self.tabText(index).endswith(strings.INFOCHAR):
            self.setTabText(index, self.tabText(index) + " " + strings.INFOCHAR)
