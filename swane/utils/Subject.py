import os
import shutil

from swane.config.preference_list import WF_PREFERENCES
from swane.utils.DataInputList import DataInputList, ImageModality
from enum import Enum, auto
from swane.config.ConfigManager import ConfigManager
from swane.utils.SubjectInputStateList import SubjectInputStateList
from swane.utils.DependencyManager import DependencyManager
from swane.workers.DicomSearchWorker import DicomSearchWorker
from PySide6.QtCore import QThreadPool
from swane import strings
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
import traceback
from threading import Thread
from swane.nipype_pipeline.workflows.freesurfer_workflow import FS_DIR
from multiprocessing import Queue
from swane.workers.WorkflowMonitorWorker import WorkflowMonitorWorker
from swane.workers.WorkflowProcess import WorkflowProcess
from swane.workers.SlicerExportWorker import SlicerExportWorker
from swane.utils.DicomTree import DicomTree


class SubjectRet(Enum):
    FolderNotFound = auto()
    PathBlankSpaces = auto()
    FolderOutsideMain = auto()
    FolderAlreadyExists = auto()
    InvalidFolderTree = auto()
    ValidFolder = auto()
    DataInputNonEmpty = auto()
    DataInputLoading = auto()
    DataInputWarningNoDicom = auto()
    DataInputWarningMultiSubj = auto()
    DataInputWarningMultiStudy = auto()
    DataInputWarningMultiSeries = auto()
    DataInputValid = auto()
    DataImportErrorVolumesMax = auto()
    DataImportErrorVolumesMin = auto()
    DataImportErrorModality = auto()
    DataImportErrorCopy = auto()
    DataImportCompleted = auto()
    GenWfMissingRequisites = auto()
    GenWfError = auto()
    GenWfCompleted = auto()
    ExecWfResume = auto()
    ExecWfResumeFreesurfer = auto()
    ExecWfStarted = auto()
    ExecWfStopped = auto()
    ExecWfStatusError = auto()


class Subject:
    GRAPH_DIR_NAME = "graph"
    GRAPH_FILE_PREFIX = "graph_"
    GRAPH_FILE_EXT = "svg"
    GRAPH_TYPE = "colored"

    def __init__(
        self, global_config: ConfigManager, dependency_manager: DependencyManager
    ):
        self.global_config: ConfigManager = global_config
        self.folder: str = None
        self.name: str = None
        self.input_state_list: SubjectInputStateList = None
        self.config: ConfigManager = None
        self.dependency_manager: DependencyManager = dependency_manager
        self.workflow: MainWorkflow = None
        self.workflow_process: WorkflowProcess = None
        self.workflow_monitor_work: WorkflowMonitorWorker = None

    def load(self, subject_folder: str) -> SubjectRet:
        """
        Load subject information from a folder, generate subject configuration and input_state_list

        Parameters
        ----------
        subject_folder: str
            The folder to scan

        Returns
        -------
        A return code from SubjectRet

        """

        check = self.check_subject_folder(subject_folder)
        if check != SubjectRet.ValidFolder:
            return check

        self.folder = subject_folder
        self.name = os.path.basename(subject_folder)
        self.input_state_list = SubjectInputStateList(
            self.dicom_folder(), self.global_config
        )
        self.create_config(self.dependency_manager)
        return SubjectRet.ValidFolder

    def prepare_scan_dicom_folders(
        self,
    ) -> tuple[dict[DataInputList, DicomSearchWorker], int]:
        """
        Generates a DicomSearchWorker for every data input

        Parameters
        ----------

        Returns
        -------
        A tuple formed by:
            A dict wich keys are data inputs and values are the relative DicomSearchWorkers
            An int with the number of files to be scanned by that worker

        """
        dicom_scanners = {}
        total_files = 0
        for data_input in self.input_state_list:
            dicom_scanners[data_input] = self.gen_dicom_search_worker(data_input)
            total_files = total_files + dicom_scanners[data_input].get_files_len()
        return dicom_scanners, total_files

    def gen_dicom_search_worker(self, data_input: DataInputList) -> DicomSearchWorker:
        """
        Generates a Worker that scan the series folder in search for DICOM files.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to check.

        Returns
        -------
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.

        """

        src_path = self.dicom_folder(data_input)
        dicom_src_work = DicomSearchWorker(src_path)
        dicom_src_work.load_dir()

        return dicom_src_work

    def execute_scan_dicom_folders(
        self,
        dicom_scanners: dict[DataInputList, DicomSearchWorker],
        status_callback: callable = None,
        progress_callback: callable = None,
    ):
        """
        Load subject information from a folder, generate subject configuration and input_state_list

        Parameters
        ----------
        dicom_scanners: dict[DataInputList, DicomSearchWorker]
            The list of DicomSearchWorker for every data input
        status_callback: callable, optional
            The function to notify return code. Default is None
        progress_callback: callable, optional
            The function to notify scan progress. Default is None

        """
        for data_input in self.input_state_list:
            if data_input in dicom_scanners:
                self.check_input_folder_step2(
                    data_input,
                    dicom_scanners[data_input],
                    progress_callback=progress_callback,
                    status_callback=status_callback,
                )
                if status_callback is not None:
                    status_callback(data_input, SubjectRet.DataInputLoading)

    def check_input_folder(
        self,
        data_input: DataInputList,
        status_callback: callable = None,
        progress_callback: callable = None,
    ):
        """
        Checks if the series folder labelled data_input contains DICOM files.
        If PersistentProgressDialog is not None, it will be used to show the scan progress.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to check.
        status_callback: callable, optional
            The function to notify update to UI. Default is None
        progress_callback : callable, optional
            A callback function to notify progress. The default is None.

        Returns
        -------
        None.

        """

        dicom_src_work = self.gen_dicom_search_worker(data_input)
        self.check_input_folder_step2(
            data_input,
            dicom_src_work,
            status_callback=status_callback,
            progress_callback=progress_callback,
        )

    def check_input_folder_step2(
        self,
        data_input: DataInputList,
        dicom_src_work: DicomSearchWorker,
        status_callback: callable = None,
        progress_callback: callable = None,
    ):
        """
        Starts the DICOM files scan Worker into the series folder on a new thread.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to check.
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.
        status_callback: callable
            The function to notify update to UI. Default is None
        progress_callback : callable, optional
            A callback function to notify progress. The default is None.

        Returns
        -------
        None.

        """

        dicom_src_work.signal.sig_finish.connect(
            lambda src, name=data_input, callback=status_callback: self.check_input_folder_step3(
                name, src, callback
            )
        )

        if progress_callback is not None:
            dicom_src_work.signal.sig_loop.connect(
                lambda i, maximum=dicom_src_work.get_files_len(): progress_callback(
                    i, maximum
                )
            )
        QThreadPool.globalInstance().start(dicom_src_work)

    def check_input_folder_step3(
        self,
        data_input: DataInputList,
        dicom_src_work: DicomSearchWorker,
        status_callback: callable = None,
    ):
        """
        Updates SWANe UI at the end of the DICOM files scan Worker execution for a subject.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to check.
        dicom_src_work : DicomSearchWorker
            The DICOM Search Worker.
        status_callback: callable.
            The function to notify update to UI. Default is None

        Returns
        -------
        None.

        """

        subjects_list = dicom_src_work.tree.get_subject_list()

        if len(subjects_list) == 0:
            status_callback(
                data_input, SubjectRet.DataInputWarningNoDicom, dicom_src_work
            )
            return

        if len(subjects_list) > 1:
            status_callback(
                data_input, SubjectRet.DataInputWarningMultiSubj, dicom_src_work
            )
            return

        studies_list = dicom_src_work.tree.get_studies_list(subjects_list[0])

        if len(studies_list) != 1:
            status_callback(
                data_input, SubjectRet.DataInputWarningMultiStudy, dicom_src_work
            )
            return

        series_list = dicom_src_work.tree.get_series_list(subjects_list[0], studies_list[0])

        if len(series_list) != 1:
            status_callback(
                data_input, SubjectRet.DataInputWarningMultiSeries, dicom_src_work
            )
            return

        series = dicom_src_work.tree.get_series(subjects_list[0], studies_list[0], series_list[0])

        self.input_state_list[data_input].loaded = True
        self.input_state_list[data_input].volumes = series.volumes
        status_callback(data_input, SubjectRet.DataInputValid, dicom_src_work)

    def dicom_import_to_folder(
        self,
        data_input: DataInputList,
        copy_list: list,
        vols: int,
        mod: str,
        force_modality: bool,
        progress_callback: callable = None,
    ) -> SubjectRet:
        """
        Copies the files inside the selected folder in the input list into the folder specified by data_input var.

        Parameters
        ----------
        data_input : DataInputList
            The name of the series to which couple the selected file.

        Returns
        -------
        None.

        """
        # series already loaded
        if self.input_state_list[data_input].loaded:
            return SubjectRet.DataInputNonEmpty
        # number of volumes check
        if data_input.value.max_volumes != -1 and vols > data_input.value.max_volumes:
            return SubjectRet.DataImportErrorVolumesMax
        if vols < data_input.value.min_volumes:
            return SubjectRet.DataImportErrorVolumesMin

        # modality check
        if (
            not data_input.value.is_image_modality(ImageModality.from_string(mod))
            and not force_modality
        ):
            return SubjectRet.DataImportErrorModality

        dest_path = os.path.join(self.dicom_folder(), str(data_input))

        try:
            for thisFile in copy_list:
                if not os.path.isfile(thisFile):
                    continue

                shutil.copy(thisFile, dest_path)
                if progress_callback is not None:
                    progress_callback(1)

            return SubjectRet.DataImportCompleted
        except:
            return SubjectRet.DataImportErrorCopy

    def create_config(self, dependency_manager: DependencyManager):
        """
        Generate the subject configuration reading its config file.

        Parameters
        ----------
        dependency_manager: DependencyManager
            the application dependency manager

        Returns
        -------
        None.

        """
        self.config = ConfigManager(self.folder)
        self.config.check_dependencies(dependency_manager)

    def dicom_folder(self, data_input: DataInputList = None) -> str:
        """
        Get a dicom folder path

        Parameters
        ----------
        data_input: DataInputList, optional
            if specified, return the relative dicom subfolder

        Returns
        -------
            The requested dicom folder path

        """

        if type(data_input) is not DataInputList:
            return os.path.join(
                self.folder, self.global_config.get_default_dicom_folder()
            )
        else:
            return os.path.join(
                self.folder,
                self.global_config.get_default_dicom_folder(),
                str(data_input),
            )

    def dicom_folder_count(self, data_input: DataInputList) -> int:
        """
        Counts files in a dicom folder

        Parameters
        ----------
        data_input: DataInputList
            the data input dicom folder to scan

        Returns
        -------
            The file count as an int

        """
        try:
            dicom_path = self.dicom_folder(data_input)
            count = len(
                [
                    entry
                    for entry in os.listdir(dicom_path)
                    if os.path.isfile(os.path.join(dicom_path, entry))
                ]
            )
            return count
        except:
            return 0

    def check_subject_folder(self, subject_folder: str) -> SubjectRet:
        """
        Check if a path is a valid subject folder

        Parameters
        ----------
        subject_folder: str
            the path to check

        Returns
        -------
            A SubjectRet code

        """
        if not os.path.exists(subject_folder):
            return SubjectRet.FolderNotFound

        if " " in subject_folder:
            return SubjectRet.PathBlankSpaces

        if not os.path.abspath(subject_folder).startswith(
            os.path.abspath(self.global_config.get_main_working_directory() + os.sep)
        ):
            return SubjectRet.FolderOutsideMain

        if not self.check_subject_subtree(subject_folder):
            return SubjectRet.InvalidFolderTree

        return SubjectRet.ValidFolder

    def clear_import_folder(self, data_input: DataInputList) -> bool:
        """
        Clears the subject series folder.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to clear.

        Returns
        -------
        False if exception raised, True otherwise.

        """
        try:
            src_path = self.dicom_folder(data_input)

            shutil.rmtree(src_path, ignore_errors=True)
            os.makedirs(src_path, exist_ok=True)

            # Reset the workflows related to the deleted DICOM images
            src_path = os.path.join(
                self.folder,
                self.name + strings.WF_DIR_SUFFIX,
                data_input.value.workflow_name,
            )
            shutil.rmtree(src_path, ignore_errors=True)
            self.input_state_list[data_input].loaded = False
            self.input_state_list[data_input].volumes = 0
            return True
        except:
            return False

    def check_subject_subtree(self, subject_folder: str) -> bool:
        """
        Check if a directory is a valid subject folder

        Parameters
        ----------
        subject_folder : str
            The directory path to check.

        Returns
        -------
        bool
            True if the directory is a valid subject folder, otherwise False.

        """

        for data_input in DataInputList:
            if not os.path.exists(
                os.path.join(
                    subject_folder,
                    self.global_config.get_default_dicom_folder(),
                    str(data_input),
                )
            ):
                return False

        return True

    def fix_subject_folder_subtree(self, subject_folder: str):
        """
        Update an existing folder with the subject subfolder structure.

        Parameters
        ----------
        subject_folder : str
            The directory path to update into a subject folder.

        Returns
        -------
        None.

        """

        for data_input in DataInputList:
            if not os.path.exists(
                os.path.join(
                    subject_folder,
                    self.global_config.get_default_dicom_folder(),
                    str(data_input),
                )
            ):
                os.makedirs(
                    os.path.join(
                        subject_folder,
                        self.global_config.get_default_dicom_folder(),
                        str(data_input),
                    ),
                    exist_ok=True,
                )

    def create_new_subject_dir(self, subject_name: str) -> SubjectRet:
        """
        Create a new subject folder and subfolders.

        Parameters
        ----------
        subject_name : str
            The subject folder name.

        Returns
        -------
        True if no Exception raised.

        """
        invalid_chars = r"\/:*?<>|"

        if subject_name is None or subject_name == "":
            return SubjectRet.FolderNotFound
        elif (
            any(char in invalid_chars for char in subject_name)
            or subject_name.isspace()
            or " " in subject_name
        ):
            return SubjectRet.PathBlankSpaces
        elif os.path.exists(
            os.path.join(self.global_config.get_main_working_directory(), subject_name)
        ):
            return SubjectRet.FolderAlreadyExists
        else:
            try:
                base_folder = os.path.abspath(
                    os.path.join(
                        self.global_config.get_main_working_directory(), subject_name
                    )
                )
                dicom_folder = os.path.join(
                    base_folder, self.global_config.get_default_dicom_folder()
                )
                for data_input in DataInputList:
                    os.makedirs(
                        os.path.join(dicom_folder, str(data_input)), exist_ok=True
                    )
                return self.load(base_folder)
            except:
                return SubjectRet.FolderNotFound

    def can_generate_workflow(self) -> bool:
        """
        Check if requisites for workflow generation are met

        Returns
        -------
        True if workflow can be generated
        """
        return (
            self.input_state_list.is_ref_loaded()
            and self.dependency_manager.is_fsl()
            and self.dependency_manager.is_dcm2niix()
        )

    def graph_dir(self) -> str:
        """
        Returns
        -------
        The path of graph directory
        """
        return os.path.join(self.folder, Subject.GRAPH_DIR_NAME)

    def graph_file(self, long_name: str):
        """
        Parameters
        ----------
        long_name: str
            The workflow complete name
        Returns
        -------
        The complete path of graph file with the specified name
        """
        graph_name = long_name.lower().replace(" ", "_")
        return os.path.join(
            self.graph_dir(),
            Subject.GRAPH_FILE_PREFIX + graph_name + "." + Subject.GRAPH_FILE_EXT,
        )

    def result_dir(self) -> str:
        """
        Returns
        -------
        The subject results directory path
        """
        return os.path.join(self.folder, MainWorkflow.Result_DIR)

    def scene_path(self) -> str:
        """
        Returns
        -------
        The slicer scene file path
        """
        return os.path.join(
            self.result_dir(), "scene." + self.global_config.get_slicer_scene_ext()
        )

    def generate_workflow(self, generate_graphs: bool = True) -> SubjectRet:
        """
        Generates and populates the Main Workflow.
        Generates the graphviz analysis graphs on a new thread.

        Parameters
        ----------
        generate_graphs: bool.
            If True, svg graphics of workflows are generated. Default is True.

        Returns
        -------
        SubjectRet corresponding to success or failure

        """

        if not self.can_generate_workflow():
            return SubjectRet.GenWfMissingRequisites

        # Main Workflow generation
        if self.workflow is None:

            # Node List population
            try:
                self.workflow = MainWorkflow(
                    name=self.name + strings.WF_DIR_SUFFIX,
                    base_dir=self.folder,
                    global_config=self.global_config,
                    subject_config=self.config,
                    dependency_manager=self.dependency_manager,
                    subject_input_state_list=self.input_state_list,
                )
            except:
                traceback.print_exc()
                # TODO: generiamo un file crash nella cartella log?
                return SubjectRet.GenWfError

        graph_dir = self.graph_dir()
        shutil.rmtree(graph_dir, ignore_errors=True)
        os.mkdir(graph_dir)

        node_list = self.workflow.get_node_array()

        # Graphviz analysis graphs drawing
        if generate_graphs:
            for node in node_list.keys():
                if len(node_list[node].node_list.keys()) > 0:
                    if self.dependency_manager.is_graphviz():
                        thread = Thread(
                            target=self.workflow.get_node(node).write_graph,
                            kwargs={
                                "graph2use": self.GRAPH_TYPE,
                                "format": Subject.GRAPH_FILE_EXT,
                                "dotfilename": os.path.join(
                                    self.graph_file(node_list[node].long_name)
                                ),
                            },
                        )
                        thread.start()

        return SubjectRet.GenWfCompleted

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

    def workflow_dir(self) -> str:
        """
        Returns
        -------
        The workflow directory path
        """
        return os.path.join(self.folder, self.name + strings.WF_DIR_SUFFIX)

    def workflow_dir_exists(self) -> bool:
        """
        Returns
        -------
        True if a previous workflow execution is found
        """
        return os.path.exists(self.workflow_dir())

    def delete_workflow_dir(self):
        """
        Delete any previous workflow execution
        """
        shutil.rmtree(self.workflow_dir(), ignore_errors=True)

    def freesurfer_dir(self) -> str:
        """
        Returns
        -------
        The freesurfer subject directory path
        """
        return os.path.join(self.folder, FS_DIR)

    def freesurfer_dir_exists(self) -> bool:
        """
        Returns
        -------
        True if freesurfer subject directory exists
        """
        return os.path.exists(self.freesurfer_dir())

    def delete_freesurfer_dir(self):
        """
        Delete any previous freesurfer run
        """
        shutil.rmtree(self.freesurfer_dir(), ignore_errors=True)

    def start_workflow(
        self,
        resume: bool = None,
        resume_freesurfer: bool = None,
        update_node_callback: callable = None,
    ) -> SubjectRet:
        """
        Start the workflow execution in a subprocess

        Parameters
        ----------
        resume: bool, optional
            If True resume previous run, if False delete them, if None and previous run is found, stops. Default is None
        resume_freesurfer: bool, optional
            If True resume previous fs run , if False delete them, if None and previous fs run is found, stops. Default is None
        update_node_callback: callable, optional
            The method to notify workflow update

        Returns
        -------
        A SubjectRet code

        """
        # Already executing workflow
        if self.is_workflow_process_alive():
            return SubjectRet.ExecWfStatusError
        # Checks for a previous workflow execution
        if self.workflow_dir_exists():
            if resume is None:
                return SubjectRet.ExecWfResume
            elif not resume:
                self.delete_workflow_dir()

        # Checks for a previous workflow FreeSurfer execution
        if self.config.get_workflow_freesurfer_pref() and self.freesurfer_dir_exists():
            if resume_freesurfer is None:
                return SubjectRet.ExecWfResumeFreesurfer
            elif not resume_freesurfer:
                self.delete_freesurfer_dir()

        queue = Queue(maxsize=500)

        # Generates a Monitor Worker to receive workflows notifications
        self.workflow_monitor_work = WorkflowMonitorWorker(queue)
        if update_node_callback is not None:
            self.workflow_monitor_work.signal.log_msg.connect(update_node_callback)
        QThreadPool.globalInstance().start(self.workflow_monitor_work)

        # Starts the workflow on a new process
        self.workflow_process = WorkflowProcess(self.name, self.workflow, queue)
        self.workflow_process.start()
        return SubjectRet.ExecWfStarted

    def stop_workflow(self) -> SubjectRet:
        """
        Stop a running workflow execution

        Returns
        -------
        A SubjectRet code

        """
        if not self.is_workflow_process_alive():
            return SubjectRet.ExecWfStatusError
        # Workflow killing
        self.workflow_process.stop_event.set()

    def reset_workflow(self, force: bool = False) -> bool:
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
        True if workflow was generated

        """

        if self.workflow is None:
            return False
        if not force and self.is_workflow_process_alive():
            return False

        self.workflow = None
        return True

    def generate_scene(self, progress_callback: callable = None):
        """
        Exports the workflow results into 3D Slicer using a new thread.

        Returns
        -------
        None.

        """

        slicer_thread = SlicerExportWorker(
            self.global_config.get_slicer_path(),
            self.result_dir(),
            self.global_config.get_slicer_scene_ext(),
            self.config
        )
        if progress_callback is not None:
            slicer_thread.signal.export.connect(progress_callback)
        QThreadPool.globalInstance().start(slicer_thread)
