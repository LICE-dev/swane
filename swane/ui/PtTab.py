import os
import shutil
import traceback
from multiprocessing import Queue
from threading import Thread

import pydicom
from PySide6.QtCore import Qt, QThreadPool, QFileSystemWatcher
from PySide6.QtGui import QFont
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QTabWidget, QWidget, QGridLayout, QLabel, QHeaderView,
                               QPushButton, QSizePolicy, QHBoxLayout,
                               QGroupBox, QVBoxLayout, QMessageBox, QListWidget,
                               QFileDialog, QTreeWidget, QErrorMessage, QFileSystemModel,
                               QTreeView, QComboBox)

from swane import strings
from swane.slicer.SlicerExportWorker import SlicerExportWorker
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
from swane.ui.workers.WorkflowGeneratorWorker import WorkflowGeneratorWorker
from swane.ui.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from swane.ui.workers.WorkflowProcess import WorkflowProcess
from swane.ui.CustomTreeWidgetItem import CustomTreeWidgetItem
from swane.ui.PersistentProgressDialog import PersistentProgressDialog
from swane.ui.PreferencesWindow import PreferencesWindow
from swane.ui.VerticalScrollArea import VerticalScrollArea
from swane.utils.ConfigManager import ConfigManager
from swane.ui.workers.DicomSearchWorker import DicomSearchWorker
from swane.nipype_pipeline.workflows.freesurfer_workflow import FS_DIR
from swane.utils.DataInput import DataInput, DataInputList
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import MonitoredMultiProcPlugin


class PtTab(QTabWidget):
    """
    Custom implementation of PySide QTabWidget to define a patient tab widget.

    """
    
    DATATAB = 0
    EXECTAB = 1
    RESULTTAB = 2
    GRAPH_DIR_NAME = "graph"
    GRAPH_FILE_PREFIX = "graph_"
    GRAPH_FILE_EXT = "svg"
    GRAPH_TYPE = "colored"
    NODE_MSG_DIVIDER = '.'

    def __init__(self, global_config, pt_folder, main_window, parent=None):
        super(PtTab, self).__init__(parent)
        self.global_config = global_config
        self.pt_folder = pt_folder
        self.pt_name = os.path.basename(pt_folder)
        self.main_window = main_window

        self.workflow = None
        self.workflow_process = None
        self.node_list = None

        dicom_dir = os.path.join(self.pt_folder, self.global_config.get_default_dicom_folder())
        self.data_input_list = DataInputList(dicom_dir)

        self.data_tab = QWidget()
        self.exec_tab = QWidget()
        self.slicer_tab = QWidget()

        self.addTab(self.data_tab, strings.pttab_data_tab_name)
        self.addTab(self.exec_tab, strings.pttab_wf_tab_name)
        self.addTab(self.slicer_tab, strings.pttab_results_tab_name)

        self.directory_watcher = QFileSystemWatcher()
        self.directory_watcher.directoryChanged.connect(self.reset_workflow)

        self.start_gen_wf_thread()

        self.data_tab_ui()
        self.exec_tab_ui()
        self.slicer_tab_ui()

        self.setTabEnabled(PtTab.EXECTAB, False)
        self.setTabEnabled(PtTab.RESULTTAB, False)

    def set_main_window(self, main_window):
        """
        Set the Main Window.

        Parameters
        ----------
        main_window : MainWindow
            The Main Window.

        Returns
        -------
        None.

        """
        
        self.main_window = main_window

    def update_node_list(self, msg: str):
        """
        Searches for the node linked to the msg arg.
        Uses the parsed msng arg to update the node status.

        Parameters
        ----------
        msg : str
            Workflow Monitor Worker message to parse.

        Returns
        -------
        None.

        """
        
        if msg == WorkflowMonitorWorker.STOP:
            errors = False
            for key in self.node_list.keys():
                self.node_list[key].node_holder.setExpanded(False)
                if not self.node_list[key].node_holder.completed:
                    errors = True
                    for subkey in self.node_list[key].node_list.keys():
                        if self.node_list[key].node_list[subkey].node_holder.art == self.main_window.ERROR_ICON_FILE:
                            self.node_list[key].node_holder.set_art(self.main_window.ERROR_ICON_FILE)
                            break

            self.setTabEnabled(PtTab.DATATAB, True)
            
            if errors:
                self.exec_button.setText(strings.pttab_wf_executed_with_error)
                self.node_button.setEnabled(True)
            else:
                self.exec_button.setText(strings.pttab_wf_executed)
                
            self.exec_button.setEnabled(False)
            self.enable_tab_if_result_dir()
            
            return

        # TODO - To be implemented for RAM usage info by each workflow
        # if msg == WorkflowProcess.WORKFLOW_INSUFFICIENT_RESOURCES:
        #     msg_box = QMessageBox()
        #     msg_box.setText(strings.pttab_wf_insufficient_resources)
        #     msg_box.exec()

        split = msg.split(PtTab.NODE_MSG_DIVIDER)

        # For every message starts by "nipype_pt_x.", remove the prefix
        split.pop(0)

        # Remaining message must be like: workflow_name.node_name.message_type
        if len(split) < 3:
            return

        if split[2] == MonitoredMultiProcPlugin.NODE_STARTED:
            icon = self.main_window.LOADING_MOVIE_FILE
        elif split[2] == MonitoredMultiProcPlugin.NODE_COMPLETED:
            icon = self.main_window.OK_ICON_FILE
        else:
            icon = self.main_window.ERROR_ICON_FILE

        self.node_list[split[0]].node_list[split[1]].node_holder.set_art(icon)

        self.node_list[split[0]].node_holder.setExpanded(True)

        if icon == self.main_window.OK_ICON_FILE:
            completed = True
            for key in self.node_list[split[0]].node_list.keys():
                if self.node_list[split[0]].node_list[key].node_holder.art != self.main_window.OK_ICON_FILE:
                    completed = False
                    break
            if completed:
                self.node_list[split[0]].node_holder.set_art(self.main_window.OK_ICON_FILE)
                self.node_list[split[0]].node_holder.setExpanded(False)
                self.node_list[split[0]].node_holder.completed = True

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

    def start_gen_wf_thread(self):
        """
        Generates the workflow object in its thread during the patient loading.
        The first workflow generation can be heavy because SWANe needs to load nypipe modules.
        If repeated, the operation is faster and therefore executed in the main thread.

        Returns
        -------
        None.

        """
        
        if not self.main_window.fsl:
            return
        
        workflow_generator_work = WorkflowGeneratorWorker(self.pt_folder)
        workflow_generator_work.signal.workflow.connect(self.set_wf)
        QThreadPool.globalInstance().start(workflow_generator_work)

    def set_wf(self, wf: MainWorkflow):
        """
        Saves the specified workflow into Main Thread and updates the UI.

        Parameters
        ----------
        wf : MainWorkflow
            The workflow passed to the Main Thread.

        Returns
        -------
        None.

        """
        
        self.workflow = wf

        try:
            self.node_button.setEnabled(True)
            self.wf_type_combo.setEnabled(True)
            self.pt_config_button.setEnabled(True)

            self.enable_exec_tab()

        except AttributeError:
            pass

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

        self.input_report = {}

        remove_list = []

        for data_input in self.data_input_list.values():

            if data_input.optional and not self.global_config.is_optional_series_enabled(data_input.name):
                remove_list.append(data_input.name)
                continue

            self.input_report[data_input.name] = [QSvgWidget(self),
                                             QLabel(data_input.label),
                                             QLabel(""),
                                             QPushButton(strings.pttab_import_button),
                                             QPushButton(strings.pttab_clear_button)]
            self.input_report[data_input.name][0].load(self.main_window.ERROR_ICON_FILE)
            self.input_report[data_input.name][0].setFixedSize(25, 25)
            if data_input.tooltip != "":
                # Add tooltips and append ⓘ character to label
                self.input_report[data_input.name][1].setText(data_input.label+" \u24D8")
                self.input_report[data_input.name][1].setToolTip(data_input.tooltip)
            self.input_report[data_input.name][1].setFont(bold_font)
            self.input_report[data_input.name][1].setAlignment(Qt.AlignLeft | Qt.AlignBottom)
            self.input_report[data_input.name][2].setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.input_report[data_input.name][2].setStyleSheet("margin-bottom: 20px")
            self.input_report[data_input.name][3].setEnabled(False)
            self.input_report[data_input.name][3].clicked.connect(
                lambda checked=None, z=data_input.name: self.dicom_import_to_folder(z))
            self.input_report[data_input.name][3].setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.input_report[data_input.name][4].setEnabled(False)
            self.input_report[data_input.name][4].clicked.connect(
                lambda checked=None, z=data_input.name: self.clear_import_folder(z))
            self.input_report[data_input.name][4].setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            folder_layout.addWidget(self.input_report[data_input.name][0], (x * 2), 0, 2, 1)
            folder_layout.addWidget(self.input_report[data_input.name][1], (x * 2), 1)

            folder_layout.addWidget(self.input_report[data_input.name][3], (x * 2), 2)
            folder_layout.addWidget(self.input_report[data_input.name][4], (x * 2), 3)

            folder_layout.addWidget(self.input_report[data_input.name][2], (x * 2) + 1, 1, 1, 3)
            x += 1

        for to_remove in remove_list:
            self.data_input_list.pop(to_remove)

        # Second Column: Series to be imported
        import_group_box = QGroupBox()
        import_layout = QVBoxLayout()
        import_group_box.setLayout(import_layout)

        scan_dicom_folder_button = QPushButton(strings.pttab_scan_dicom_button)
        scan_dicom_folder_button.clicked.connect(self.scan_dicom_folder)

        self.importable_series_list = QListWidget()
        import_layout.addWidget(scan_dicom_folder_button)
        import_layout.addWidget(self.importable_series_list)

        # Adding data_input columns to Main Layout
        layout.addWidget(scroll_area, stretch=1)
        layout.addWidget(import_group_box, stretch=1)
        self.data_tab.setLayout(layout)

    def dicom_import_to_folder(self, input_name: str):
        """
        Copies the files inside the selected folder in the input list into the folder specified by input_name var.

        Parameters
        ----------
        input_name : str
            The name of the series to which couple the selected file.

        Returns
        -------
        None.

        """
        
        if self.importable_series_list.currentRow() == -1:
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_selected_series_error)
            msg_box.exec()
            return

        import shutil
        dest_path = os.path.join(self.pt_folder,
                                 self.global_config.get_default_dicom_folder(), input_name)
        found_mod = self.final_series_list[self.importable_series_list.currentRow()][0].split("-")[1].upper()

        if not self.data_input_list[input_name].is_image_modality(found_mod):
            msg_box = QMessageBox()
            msg_box.setText(strings.pttab_wrong_type_check_msg % (found_mod, self.data_input_list[input_name].image_modality))
            msg_box.setText(strings.pttab_wrong_type_check)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setDefaultButton(QMessageBox.StandardButton.No)
            ret = msg_box.exec()
            
            if ret == QMessageBox.StandardButton.No:
                return

        copy_list = self.final_series_list[self.importable_series_list.currentRow()][1]

        progress = PersistentProgressDialog(strings.pttab_dicom_copy, 0, len(copy_list) + 1, self)
        progress.show()

        self.input_report[input_name][0].load(self.main_window.LOADING_MOVIE_FILE)

        for thisFile in copy_list:
            if not os.path.isfile(thisFile):
                continue
            
            shutil.copy(thisFile, dest_path)
            progress.increase_value(1)

        progress.setRange(0, 0)
        progress.setLabelText(strings.pttab_dicom_check)

        self.check_input_folder(input_name, progress)
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
            self.importable_series_list.clear()
            self.final_series_list = []
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

        for index, label in enumerate(ConfigManager.WORKFLOW_TYPES):
            self.wf_type_combo.insertItem(index, label)

        layout.addWidget(self.wf_type_combo, 0, 0)

        self.node_button = QPushButton(strings.GENBUTTONTEXT)
        self.node_button.clicked.connect(self.gen_wf)
        if self.workflow is None:
            self.node_button.setEnabled(False)

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
        self.pt_config_button = QPushButton(strings.PTCONFIGBUTTONTEXT)
        self.pt_config_button.clicked.connect(self.edit_pt_config)
        layout.addWidget(self.pt_config_button, 0, 1)

        self.exec_button = QPushButton(strings.EXECBUTTONTEXT)
        self.exec_button.clicked.connect(self.start_workflow_thread)
        self.exec_button.setEnabled(False)

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
        
        preference_window = PreferencesWindow(self.pt_config, self.data_input_list, self)
        ret = preference_window.exec()
        if ret != 0:
            self.reset_workflow()

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
        
        self.pt_config.set_wf_option(index)
        self.pt_config.save()
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
        
        if not self.main_window.fsl:
            error_dialog = QErrorMessage(parent=self)
            error_dialog.showMessage(strings.pttab_missing_fsl_error)
            return

        # Main Workflow generation
        if self.workflow is None:
            self.workflow = MainWorkflow(name=self.pt_name + WorkflowGeneratorWorker.WF_DIR_SUFFIX, base_dir=self.pt_folder)
        
        # Node List population
        try:
            self.workflow.add_input_folders(self.global_config, self.pt_config, self.data_input_list)
        except:
            error_dialog = QErrorMessage(parent=self)
            error_dialog.showMessage(strings.pttab_wf_gen_error)
            traceback.print_exc()
            # TODO: generiamo un file crash nella cartella log?
            return
        
        self.node_list = self.workflow.get_node_array()
        self.node_list_treeWidget.clear()

        graph_dir = os.path.join(self.pt_folder, PtTab.GRAPH_DIR_NAME)
        shutil.rmtree(graph_dir, ignore_errors=True)
        os.mkdir(graph_dir)
        
        # Graphviz analysis graphs drawing
        for node in self.node_list.keys():
            self.node_list[node].node_holder = CustomTreeWidgetItem(self.node_list_treeWidget, self.node_list_treeWidget, self.node_list[node].long_name)
            if len(self.node_list[node].node_list.keys()) > 0:
                if self.main_window.graphviz:
                    graph_name = self.node_list[node].long_name.lower().replace(" ", "_")
                    thread = Thread(target=self.workflow.get_node(node).write_graph,
                                    kwargs={'graph2use': self.GRAPH_TYPE, 'format': PtTab.GRAPH_FILE_EXT,
                                            'dotfilename': os.path.join(graph_dir,
                                                                        PtTab.GRAPH_FILE_PREFIX + graph_name + '.dot')})
                    thread.start()
                    
                for sub_node in self.node_list[node].node_list.keys():
                    self.node_list[node].node_list[sub_node].node_holder = CustomTreeWidgetItem(self.node_list[node].node_holder, self.node_list_treeWidget, self.node_list[node].node_list[sub_node].long_name)
        
        # UI updating
        self.exec_button.setEnabled(True)
        self.exec_button.setText(strings.EXECBUTTONTEXT)
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
        
        if self.main_window.graphviz and item.parent() is None:
            file = os.path.join(self.pt_folder, PtTab.GRAPH_DIR_NAME, PtTab.GRAPH_FILE_PREFIX + item.get_text().lower().replace(" ", "_") + '.'
                                + PtTab.GRAPH_FILE_EXT)
            self.exec_graph.load(file)
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

    def is_workflow_process_alive(self) -> bool:
        """
        Checks if a workflow is in execution.

        Returns
        -------
        bool
            True if the workflow is executing, elsewise False.

        """
        
        try:
            if self.workflow_process is None:
                return False
            
            return self.workflow_process.is_alive()
        
        except AttributeError:
            return False

    def start_workflow_thread(self):
        """
        If the workflow is not started, executes it.
        If the workflow is executing, kills it.

        Returns
        -------
        None.

        """
        
        # Workflow not started
        if not self.is_workflow_process_alive():
            workflow_dir = os.path.join(self.pt_folder, self.pt_name + WorkflowGeneratorWorker.WF_DIR_SUFFIX)
            # Checks for a previous workflow execution
            if os.path.exists(workflow_dir):
                # If yes, asks for workflow resume or reset
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
                
                if ret == QMessageBox.StandardButton.No:
                    shutil.rmtree(workflow_dir, ignore_errors=True)

            fsdir = os.path.join(self.pt_folder, FS_DIR)
            # Checks for a previous workflow FreeSurfer execution
            if self.pt_config.get_pt_wf_freesurfer() and os.path.exists(fsdir):
                # If yes, asks for workflow resume or reset
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
                
                if ret == QMessageBox.StandardButton.No:
                    shutil.rmtree(fsdir, ignore_errors=True)

            queue = Queue(maxsize=500)
            
            # Generates a Monitor Worker to receive workflows notifications
            workflow_monitor_work = WorkflowMonitorWorker(queue)
            workflow_monitor_work.signal.log_msg.connect(self.update_node_list)
            QThreadPool.globalInstance().start(workflow_monitor_work)
            
            # Starts the workflow on a new process
            self.workflow_process = WorkflowProcess(self.pt_name, self.workflow, queue)
            self.workflow_process.start()
            
            # UI updating
            self.exec_button.setText(strings.EXECBUTTONTEXT_STOP)
            self.setTabEnabled(PtTab.DATATAB, False)
            self.setTabEnabled(PtTab.RESULTTAB, False)
            self.wf_type_combo.setEnabled(False)
            self.pt_config_button.setEnabled(False)

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
            
            # Workflow killing
            self.workflow_process.stop_event.set()
            
            # UI updating
            self.remove_running_icon()
            self.exec_button.setText(strings.EXECBUTTONTEXT)
            self.setTabEnabled(PtTab.DATATAB, True)
            self.reset_workflow(force=True)
            self.enable_tab_if_result_dir()

    def slicer_tab_ui(self):
        """
        Generates the Results tab UI.

        Returns
        -------
        None.

        """
        
        slicer_tab_layout = QGridLayout()
        self.slicer_tab.setLayout(slicer_tab_layout)

        self.export_results_button = QPushButton(strings.pttab_results_button)
        self.export_results_button.clicked.connect(self.slicer_thread)
        self.export_results_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        if self.global_config.get_slicer_path() == '' or not os.path.exists(self.global_config.get_slicer_path()):
            self.export_results_button.setEnabled(False)
        slicer_tab_layout.addWidget(self.export_results_button, 0, 0)

        self.results_model = QFileSystemModel()
        self.result_tree = QTreeView(parent=self)
        self.result_tree.setModel(self.results_model)

        slicer_tab_layout.addWidget(self.result_tree, 1, 0)

    def slicer_thread(self):
        """
        Exports the workflow results into 3D Slicer using a new thread.

        Returns
        -------
        None.

        """
        
        progress = PersistentProgressDialog(strings.pttab_exporting_start, 0, 0, parent=self)
        progress.show()

        slicer_thread = SlicerExportWorker(self.global_config.get_slicer_path(), self.pt_folder,
                                           self.global_config.get_slicer_scene_ext(), parent=self)
        slicer_thread.signal.export.connect(lambda msg: self.slicer_thread_signal(msg, progress))
        QThreadPool.globalInstance().start(slicer_thread)

    def slicer_thread_signal(self, msg: str, progress: PersistentProgressDialog):
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

    def load_pt(self):
        """
        Loads the Patient configuration and folder.

        Returns
        -------
        None.

        """
        
        dicom_scanners = {}
        total_files = 0

        # Config import absed on nipype_pipeline
        self.pt_config = ConfigManager(self.pt_folder, self.main_window.freesurfer)
        self.wf_type_combo.setCurrentIndex(self.pt_config.get_pt_wf_type())
        # Set after patient loading to prevent the onchanged fire on previous line command
        self.wf_type_combo.currentIndexChanged.connect(self.on_wf_type_changed)

        for data_input in self.data_input_list.values():
            input_name = data_input.name
            dicom_scanners[input_name] = self.check_input_folder_step1(input_name)
            total_files = total_files + dicom_scanners[input_name].get_files_len()

        if total_files > 0:
            progress = PersistentProgressDialog(strings.pttab_pt_loading, 0, 0, parent=self.parent())
            progress.show()
            progress.setMaximum(total_files)
        else:
            progress = None

        for data_input in self.data_input_list.values():
            input_name = data_input.name
            self.input_report[input_name][0].load(self.main_window.LOADING_MOVIE_FILE)
            self.check_input_folder_step2(input_name, dicom_scanners[input_name], progress)
            self.directory_watcher.addPath(
                os.path.join(self.pt_folder, self.global_config.get_default_dicom_folder(), input_name))

        self.setTabEnabled(PtTab.DATATAB, True)
        self.setCurrentWidget(self.data_tab)

        self.importable_series_list.clear()
        self.reset_workflow()

        self.enable_tab_if_result_dir()

    def enable_tab_if_result_dir(self):
        """
        Enables Results tab, if any.

        Returns
        -------
        None.

        """
        scene_dir = os.path.join(self.pt_folder, MainWorkflow.SCENE_DIR)
        
        if os.path.exists(scene_dir):
            self.setTabEnabled(PtTab.RESULTTAB, True)
            self.results_model.setRootPath(scene_dir)
            index_root = self.results_model.index(self.results_model.rootPath())
            self.result_tree.setRootIndex(index_root)
        else:
            self.setTabEnabled(PtTab.RESULTTAB, False)

    def check_input_folder_step1(self, input_name: str) -> DicomSearchWorker:
        """
        Generates a Worker that scan the series folder in search for DICOM files.

        Parameters
        ----------
        input_name : str
            The series folder name to check.

        Returns
        -------
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.

        """
        
        src_path = os.path.join(self.pt_folder,
                                self.global_config.get_default_dicom_folder(), input_name)
        dicom_src_work = DicomSearchWorker(src_path)
        dicom_src_work.load_dir()
        
        return dicom_src_work

    def check_input_folder_step2(self, input_name: str, dicom_src_work: DicomSearchWorker, progress: PersistentProgressDialog=None):
        """
        Starts the DICOM files scan Worker into the series folder on a new thread.

        Parameters
        ----------
        input_name : str
            The series folder name to check.
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.
        progress : PersistentProgressDialog, optional
            The progress dialog. The default is None.

        Returns
        -------
        None.

        """
        
        dicom_src_work.signal.sig_finish.connect(lambda src, name=input_name: self.check_input_folder_step3(name, src))
        
        if progress is not None:
            if progress.maximum() == 0:
                progress.setMaximum(dicom_src_work.get_files_len())
            dicom_src_work.signal.sig_loop.connect(lambda i: progress.increase_value(i))
            
        QThreadPool.globalInstance().start(dicom_src_work)

    def check_input_folder_step3(self, input_name: str, dicom_src_work: DicomSearchWorker):
        """
        Updates SWANe UI at the end of the DICOM files scan Worker execution for a patient.

        Parameters
        ----------
        input_name : str
            The series folder name to check.
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.

        Returns
        -------
        None.

        """
        
        src_path = dicom_src_work.dicom_dir
        pt_list = dicom_src_work.get_patient_list()

        if len(pt_list) == 0:
            self.set_error(input_name, strings.pttab_no_dicom_error + src_path)
            return

        if len(pt_list) > 1:
            self.set_warn(input_name, strings.pttab_multi_pt_error + src_path)
            return
        
        exam_list = dicom_src_work.get_exam_list(pt_list[0])
        
        if len(exam_list) != 1:
            self.set_warn(input_name, strings.pttab_multi_exam_error + src_path)
            return
        
        series_list = dicom_src_work.get_series_list(pt_list[0], exam_list[0])
        
        if len(series_list) != 1:
            self.set_warn(input_name, strings.pttab_multi_series_error + src_path)
            return

        image_list = dicom_src_work.get_series_files(pt_list[0], exam_list[0], series_list[0])
        ds = pydicom.read_file(image_list[0], force=True)
        mod = ds.Modality
        
        if mod in DataInput.IMAGE_MODALITY_RENAME_LIST:
            mod = DataInput.IMAGE_MODALITY_RENAME_LIST[mod]
            
        self.set_ok(input_name, str(ds.PatientName) + "-" + mod + "-" + ds.SeriesDescription + ": " + str(
            len(image_list)) + " images")

        self.data_input_list[input_name].loaded = True

        self.enable_exec_tab()

    def check_input_folder(self, input_name: str, progress: PersistentProgressDialog=None):
        """
        Checks if the series folder labelled input_name contains DICOM files.
        If PersistentProgressDialog is not None, it will be used to show the scan progress.

        Parameters
        ----------
        input_name : str
            The series folder name to check.
        progress : PersistentProgressDialog, optional
            The progress dialog. The default is None.

        Returns
        -------
        None.

        """
        
        dicom_src_work = self.check_input_folder_step1(input_name)
        self.check_input_folder_step2(input_name, dicom_src_work, progress)

    def clear_import_folder(self, input_name: str):
        """
        Clears the patient series folder.

        Parameters
        ----------
        input_name : str
            The series folder name to clear.

        Returns
        -------
        None.

        """

        src_path = os.path.join(self.pt_folder,
                                self.global_config.get_default_dicom_folder(), input_name)

        progress = PersistentProgressDialog(strings.pttab_dicom_clearing + src_path, 0, 0, self)
        progress.show()

        import shutil
        shutil.rmtree(src_path, ignore_errors=True)
        os.makedirs(src_path, exist_ok=True)

        # Reset the workflows related to the deleted DICOM images
        src_path = os.path.join(self.pt_folder, self.pt_name + WorkflowGeneratorWorker.WF_DIR_SUFFIX,
                                self.data_input_list[input_name].wf_name)
        shutil.rmtree(src_path, ignore_errors=True)

        self.set_error(input_name, strings.pttab_no_dicom_error + src_path)
        self.data_input_list[input_name].loaded = False
        self.enable_exec_tab()

        progress.accept()
        
        self.reset_workflow()

    def reset_workflow(self, force: bool=False):
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
        
        if self.workflow is None:
            return
        if not force and self.is_workflow_process_alive():
            return

        self.workflow = None
        self.node_list_treeWidget.clear()
        self.exec_graph.load(self.main_window.VOID_SVG_FILE)
        self.exec_button.setEnabled(False)
        self.exec_button.setText(strings.EXECBUTTONTEXT)
        self.node_button.setEnabled(True)
        self.wf_type_combo.setEnabled(True)
        self.pt_config_button.setEnabled(True)

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

                if mod in DataInput.IMAGE_MODALITY_RENAME_LIST:
                    mod = DataInput.IMAGE_MODALITY_RENAME_LIST[mod]

                self.final_series_list.append(
                    [str(ds.PatientName) + "-" + mod + "-" + ds.SeriesDescription + ": " + str(
                        len(image_list)) + " images", image_list])
                del image_list

        for series in self.final_series_list:
            self.importable_series_list.addItem(series[0])

    def set_warn(self, input_name: str, msg: str):
        """
        Set a warning message and icon near a series label.

        Parameters
        ----------
        input_name : str
            The series label.
        msg : str
            The warning message.

        Returns
        -------
        None.

        """
        
        self.input_report[input_name][0].load(self.main_window.WARNING_ICON_FILE)
        self.input_report[input_name][0].setFixedSize(25, 25)
        self.input_report[input_name][0].setToolTip(msg)
        self.input_report[input_name][3].setEnabled(False)
        self.input_report[input_name][4].setEnabled(True)
        self.input_report[input_name][2].setText("")

    def set_error(self, input_name: str, msg: str):
        """
        Set an error message and icon near a series label.

        Parameters
        ----------
        input_name : str
            The series label.
        msg : str
            The error message.

        Returns
        -------
        None.

        """
        
        self.input_report[input_name][0].load(self.main_window.ERROR_ICON_FILE)
        self.input_report[input_name][0].setFixedSize(25, 25)
        self.input_report[input_name][0].setToolTip(msg)
        self.input_report[input_name][3].setEnabled(True)
        self.input_report[input_name][4].setEnabled(False)
        self.input_report[input_name][2].setText("")

    def set_ok(self, input_name: str, msg: str):
        """
        Set a success message and icon near a series label.

        Parameters
        ----------
        input_name : str
            The series label.
        msg : str
            The success message.

        Returns
        -------
        None.

        """
        
        self.input_report[input_name][0].load(self.main_window.OK_ICON_FILE)
        self.input_report[input_name][0].setFixedSize(25, 25)
        self.input_report[input_name][0].setToolTip("")
        self.input_report[input_name][3].setEnabled(False)
        self.input_report[input_name][4].setEnabled(True)
        self.input_report[input_name][2].setText(msg)

    def enable_exec_tab(self):
        """
        Enables the Execute Workflow tab into the UI.

        Returns
        -------
        None.

        """
        
        enable = self.data_input_list.is_ref_loaded() and self.main_window.fsl and self.main_window.dcm2niix
        self.setTabEnabled(PtTab.EXECTAB, enable)
