import os
import shutil
from swane.utils.DataInputList import DataInputList, ImageModality
from enum import Enum, auto
from swane.config.ConfigManager import ConfigManager
from swane.utils.PatientInputStateList import PatientInputStateList
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
from swane.config.preference_list import SLICER_EXTENSIONS
from swane.workers.SlicerExportWorker import SlicerExportWorker


class PatientRet(Enum):
    FolderNotFound = auto()
    PathBlankSpaces = auto()
    FolderOutsideMain = auto()
    FolderAlreadyExists = auto()
    InvalidFolderTree = auto()
    ValidFolder = auto()
    DataInputLoading = auto()
    DataInputWarningNoDicom = auto()
    DataInputWarningMultiPt = auto()
    DataInputWarningMultiExam = auto()
    DataInputWarningMultiSeries = auto()
    DataInputValid = ()
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


class Patient:
    GRAPH_DIR_NAME = "graph"
    GRAPH_FILE_PREFIX = "graph_"
    GRAPH_FILE_EXT = "svg"
    GRAPH_TYPE = "colored"

    def __init__(self, global_config: ConfigManager, dependency_manager: DependencyManager):
        self.global_config: ConfigManager = global_config
        self.folder: str | None = None
        self.name: str | None = None
        self.input_state_list: PatientInputStateList | None = None
        self.config: ConfigManager | None = None
        self.dependency_manager: DependencyManager = dependency_manager
        self.workflow: MainWorkflow | None = None
        self.workflow_process: WorkflowProcess | None = None
        self.workflow_monitor_work: WorkflowMonitorWorker | None = None

    def load(self, patient_folder: str) -> PatientRet:
        # Load patient information from a folder, generate patient configuration and
        check = self.check_patient_folder(patient_folder)
        if check != PatientRet.ValidFolder:
            return check

        self.folder = patient_folder
        self.name = os.path.basename(patient_folder)
        self.input_state_list = PatientInputStateList(self.dicom_folder(), self.global_config)
        self.create_config(self.dependency_manager)
        return PatientRet.ValidFolder

    def prepare_scan_dicom_folders(self) -> tuple[dict[DataInputList, DicomSearchWorker], int]:
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

    def execute_scan_dicom_folders(self, dicom_scanners: dict[DataInputList, DicomSearchWorker], status_callback: callable = None, progress_callback: callable = None):
        for data_input in self.input_state_list:
            if data_input in dicom_scanners:
                self.check_input_folder_step2(data_input, dicom_scanners[data_input], progress_callback=progress_callback, status_callback=status_callback)
                if status_callback is not None:
                    status_callback(data_input, PatientRet.DataInputLoading)

    def check_input_folder(self, data_input: DataInputList, status_callback: callable = None,
                           progress_callback: callable = None):
        """
        Checks if the series folder labelled data_input contains DICOM files.
        If PersistentProgressDialog is not None, it will be used to show the scan progress.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to check.
        status_callback: callable
            The function to notify update to UI. Default is None
        progress_callback : callable, optional
            A callback function to notify progress. The default is None.

        Returns
        -------
        None.

        """

        dicom_src_work = self.gen_dicom_search_worker(data_input)
        self.check_input_folder_step2(data_input, dicom_src_work, status_callback=status_callback, progress_callback=progress_callback)

    def check_input_folder_step2(self, data_input: DataInputList, dicom_src_work: DicomSearchWorker, status_callback: callable = None,
                                 progress_callback: callable = None):
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

        dicom_src_work.signal.sig_finish.connect(lambda src, name=data_input, callback=status_callback: self.check_input_folder_step3(name, src, callback))

        if progress_callback is not None:
            dicom_src_work.signal.sig_loop.connect(lambda i, maximum=dicom_src_work.get_files_len(): progress_callback(i, maximum))
        QThreadPool.globalInstance().start(dicom_src_work)

    def check_input_folder_step3(self, data_input: DataInputList, dicom_src_work: DicomSearchWorker, status_callback: callable = None):
        """
        Updates SWANe UI at the end of the DICOM files scan Worker execution for a patient.

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

        patient_list = dicom_src_work.get_patient_list()

        if len(patient_list) == 0:
            status_callback(data_input, PatientRet.DataInputWarningNoDicom, dicom_src_work)
            return

        if len(patient_list) > 1:
            status_callback(data_input, PatientRet.DataInputWarningMultiPt, dicom_src_work)
            return

        exam_list = dicom_src_work.get_exam_list(patient_list[0])

        if len(exam_list) != 1:
            status_callback(data_input, PatientRet.DataInputWarningMultiExam, dicom_src_work)
            return

        series_list = dicom_src_work.get_series_list(patient_list[0], exam_list[0])

        if len(series_list) != 1:
            status_callback(data_input, PatientRet.DataInputWarningMultiSeries, dicom_src_work)
            return
        self.input_state_list[data_input].loaded = True
        self.input_state_list[data_input].volumes = dicom_src_work.get_series_nvol(patient_list[0], exam_list[0],series_list[0])
        status_callback(data_input, PatientRet.DataInputValid, dicom_src_work)

    def dicom_import_to_folder(self, data_input: DataInputList, copy_list: list, vols: int, mod: str, force_modality: bool, progress_callback: callable = None) -> PatientRet:
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
        # number of volumes check
        if data_input.value.max_volumes != -1 and vols > data_input.value.max_volumes:
            return PatientRet.DataImportErrorVolumesMax
        if vols < data_input.value.min_volumes:
            return PatientRet.DataImportErrorVolumesMin

        # modality check
        if not data_input.value.is_image_modality(ImageModality.from_string(mod)) and not force_modality:
            return PatientRet.DataImportErrorModality

        dest_path = os.path.join(self.dicom_folder(), str(data_input))

        try:
            for thisFile in copy_list:
                if not os.path.isfile(thisFile):
                    continue

                shutil.copy(thisFile, dest_path)
                if progress_callback is not None:
                    progress_callback(1)

            return PatientRet.DataImportCompleted
        except:
            return PatientRet.DataImportErrorCopy

    def create_config(self, dependency_manager: DependencyManager):
        self.config = ConfigManager(self.folder)
        self.config.check_dependencies(dependency_manager)

    def dicom_folder(self, data_input: DataInputList = None) -> str:
        if data_input is None:
            return os.path.join(self.folder, self.global_config.get_default_dicom_folder())
        else:
            return os.path.join(self.folder, self.global_config.get_default_dicom_folder(), str(data_input))

    def dicom_folder_count(self, data_input: DataInputList) -> int:
        try:
            dicom_path = self.dicom_folder(data_input)
            count = len(
                [entry for entry in os.listdir(dicom_path) if os.path.isfile(os.path.join(dicom_path, entry))])
            return count
        except:
            return 0

    def check_patient_folder(self, patient_folder: str):
        if not os.path.exists(patient_folder):
            return PatientRet.FolderNotFound

        if ' ' in patient_folder:
            return PatientRet.PathBlankSpaces

        if not os.path.abspath(patient_folder).startswith(os.path.abspath(self.global_config.get_main_working_directory() + os.sep)):
            return PatientRet.FolderOutsideMain

        if not self.check_patient_subtree(patient_folder):
            return PatientRet.InvalidFolderTree

        return PatientRet.ValidFolder

    def clear_import_folder(self, data_input: DataInputList) -> bool:
        """
        Clears the patient series folder.

        Parameters
        ----------
        data_input : DataInputList
            The series folder name to clear.

        Returns
        -------
        False is exception raised, True otherwise.

        """
        try:
            src_path = self.dicom_folder(data_input)

            shutil.rmtree(src_path, ignore_errors=True)
            os.makedirs(src_path, exist_ok=True)

            # Reset the workflows related to the deleted DICOM images
            src_path = os.path.join(self.folder, self.name + strings.WF_DIR_SUFFIX,
                                    data_input.value.wf_name)
            shutil.rmtree(src_path, ignore_errors=True)
            return True
        except:
            return False

    def check_patient_subtree(self, patient_folder: str) -> bool:
        """
        Check if a directory is a valid patient folder

        Parameters
        ----------
        patient_folder : str
            The directory path to check.

        Returns
        -------
        bool
            True if the directory is a valid patient folder, otherwise False.

        """

        for data_input in DataInputList:
            if not os.path.exists(os.path.join(patient_folder, self.global_config.get_default_dicom_folder(), str(data_input))):
                return False

        return True

    def fix_patient_folder_subtree(self, patient_folder: str):
        """
        Update an existing folder with the patient subfolder structure.

        Parameters
        ----------
        patient_folder : str
            The directory path to update into a patient folder.

        Returns
        -------
        None.

        """

        for data_input in DataInputList:
            if not os.path.exists(
                    os.path.join(patient_folder, self.global_config.get_default_dicom_folder(), str(data_input))):
                os.makedirs(os.path.join(patient_folder, self.global_config.get_default_dicom_folder(), str(data_input)),
                            exist_ok=True)

    def create_new_patient_dir(self, patient_name: str) -> PatientRet:
        """
        Create a new patient folder and subfolders.

        Parameters
        ----------
        patient_name : str
            The patient folder name.

        Returns
        -------
        True if no Exception raised.

        """
        invalid_chars = r'\/:*?<>|'

        if patient_name is None or patient_name == "":
            return PatientRet.FolderNotFound
        elif any(char in invalid_chars for char in patient_name) or patient_name.isspace() or ' ' in patient_name:
            return PatientRet.PathBlankSpaces
        elif os.path.exists(os.path.join(self.global_config.get_main_working_directory(), patient_name)):
            return PatientRet.FolderAlreadyExists
        else:
            try:
                base_folder = os.path.abspath(os.path.join(self.global_config.get_main_working_directory(), patient_name))
                dicom_folder = os.path.join(base_folder, self.global_config.get_default_dicom_folder())
                for data_input in DataInputList:
                    os.makedirs(os.path.join(dicom_folder, str(data_input)), exist_ok=True)
                return self.load(base_folder)
            except:
                return PatientRet.FolderNotFound

    def can_generate_workflow(self):
        return self.input_state_list.is_ref_loaded() and self.dependency_manager.is_fsl() and self.dependency_manager.is_dcm2niix()

    def graph_dir(self):
        return os.path.join(self.folder, Patient.GRAPH_DIR_NAME)

    def graph_file(self, long_name: str):
        """

        Parameters
        ----------
        long_name: str
            The workflow complete name
        Returns
        -------

        """
        graph_name = long_name.lower().replace(" ", "_")
        return os.path.join(self.graph_dir(), Patient.GRAPH_FILE_PREFIX + graph_name + "." + Patient.GRAPH_FILE_EXT)

    def result_dir(self):
        return os.path.join(self.folder, MainWorkflow.Result_DIR)

    def scene_path(self):
        return os.path.join(self.result_dir(), "scene." + SLICER_EXTENSIONS[int(self.global_config.get_slicer_scene_ext())])

    def generate_workflow(self, generate_praphs: bool = True) -> PatientRet:
        """
        Generates and populates the Main Workflow.
        Generates the graphviz analysis graphs on a new thread.

        Parameters
        ----------
        generate_praphs: bool.
            If True, svg graphics of workflows are generated. Default is True.

        Returns
        -------
        PatientRet corresponging to succes or failure

        """

        if not self.can_generate_workflow():
            return PatientRet.GenWfMissingRequisites

        # Main Workflow generation
        if self.workflow is None:
            self.workflow = MainWorkflow(name=self.name + strings.WF_DIR_SUFFIX, base_dir=self.folder)

        # Node List population
        try:
            self.workflow.add_input_folders(self.global_config, self.config,
                                            self.dependency_manager, self.input_state_list)
        except:
            traceback.print_exc()
            # TODO: generiamo un file crash nella cartella log?
            return PatientRet.GenWfError

        graph_dir = self.graph_dir()
        shutil.rmtree(graph_dir, ignore_errors=True)
        os.mkdir(graph_dir)

        node_list = self.workflow.get_node_array()

        # Graphviz analysis graphs drawing
        if generate_praphs:
            for node in node_list.keys():
                if len(node_list[node].node_list.keys()) > 0:
                    if self.dependency_manager.is_graphviz():
                        thread = Thread(target=self.workflow.get_node(node).write_graph,
                                        kwargs={'graph2use': self.GRAPH_TYPE, 'format': Patient.GRAPH_FILE_EXT,
                                                'dotfilename': os.path.join(self.graph_file(node_list[node].long_name)),
                                                })
                        thread.start()

        return PatientRet.GenWfCompleted

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

    def workflow_dir(self):
        return os.path.join(self.folder, self.name + strings.WF_DIR_SUFFIX)

    def workflow_dir_exists(self):
        return os.path.exists(self.workflow_dir())

    def delete_workflow_dir(self):
        shutil.rmtree(self.workflow_dir(), ignore_errors=True)

    def freesurfer_dir(self):
        return os.path.join(self.folder, FS_DIR)

    def freesurfer_dir_exists(self):
        return os.path.exists(self.freesurfer_dir())

    def delete_freesurfer_dir(self):
        shutil.rmtree(self.freesurfer_dir(), ignore_errors=True)

    def start_workflow(self, resume: bool = None, resume_freesurfer: bool = None, update_node_callback: callable = None) -> PatientRet:
        # Already executing workflow
        if self.is_workflow_process_alive():
            return PatientRet.ExecWfStatusError
        # Checks for a previous workflow execution
        if self.workflow_dir_exists():
            if resume is None:
                return PatientRet.ExecWfResume
            elif not resume:
                self.delete_workflow_dir()

        # Checks for a previous workflow FreeSurfer execution
        if self.config.get_workflow_freesurfer_pref() and self.freesurfer_dir_exists():
            if resume_freesurfer is None:
                return PatientRet.ExecWfResumeFreesurfer
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
        return PatientRet.ExecWfStarted

    def stop_workflow(self) -> PatientRet:
        if not self.is_workflow_process_alive():
            return PatientRet.ExecWfStatusError
        # Workflow killing
        self.workflow_process.stop_event.set()

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

        slicer_thread = SlicerExportWorker(self.global_config.get_slicer_path(), self.folder,
                                           self.global_config.get_slicer_scene_ext(), parent=self)
        if progress_callback is not None:
            slicer_thread.signal.export.connect(progress_callback)
        QThreadPool.globalInstance().start(slicer_thread)
