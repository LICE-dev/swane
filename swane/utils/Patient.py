import os
import shutil
from swane.utils.DataInputList import DataInputList, ImageModality
from enum import Enum, auto
from swane.config.ConfigManager import ConfigManager
from swane.utils.PatientInputStateList import PatientInputStateList
from swane.utils.DependencyManager import DependencyManager
from swane.ui.workers.DicomSearchWorker import DicomSearchWorker
from PySide6.QtCore import QThreadPool
from swane import strings


class PatientRet(Enum):
    FolderNotFound = auto()
    PathBlankSpaces = auto()
    FolderOutsideMain = auto()
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


class Patient:

    def __init__(self, global_config: ConfigManager):
        self.folder = None
        self.name = None
        self.global_config = global_config
        self.input_state_list = None
        self.config = None

    def load(self, pt_folder: str, dependency_manager: DependencyManager) -> PatientRet:
        # Load patient information from a folder, generate patient configuration and
        check = self.check_pt_folder(pt_folder)
        if check != PatientRet.ValidFolder:
            return check

        self.folder = pt_folder
        self.name = os.path.basename(pt_folder)
        self.input_state_list = PatientInputStateList(self.dicom_folder(), self.global_config)
        self.create_config(dependency_manager)
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

        src_path = os.path.join(self.dicom_folder(), str(data_input))
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

        pt_list = dicom_src_work.get_patient_list()

        if len(pt_list) == 0:
            status_callback(data_input, PatientRet.DataInputWarningNoDicom, dicom_src_work)
            return

        if len(pt_list) > 1:
            status_callback(data_input, PatientRet.DataInputWarningMultiPt, dicom_src_work)
            return

        exam_list = dicom_src_work.get_exam_list(pt_list[0])

        if len(exam_list) != 1:
            status_callback(data_input, PatientRet.DataInputWarningMultiExam, dicom_src_work)
            return

        series_list = dicom_src_work.get_series_list(pt_list[0], exam_list[0])

        if len(series_list) != 1:
            status_callback(data_input, PatientRet.DataInputWarningMultiSeries, dicom_src_work)
            return

        status_callback(data_input, PatientRet.DataInputValid, dicom_src_work)

        self.input_state_list[data_input].loaded = True
        self.input_state_list[data_input].volumes = dicom_src_work.get_series_nvol(pt_list[0], exam_list[0],
                                                                                   series_list[0])

    def dicom_import_to_folder(self, data_input: DataInputList, copy_list: list, vols: int, mod: str, force_modality: bool, progress_callback: callable) -> PatientRet:
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
                progress_callback(1)

            return PatientRet.DataImportCompleted
        except:
            return PatientRet.DataImportErrorCopy

    def create_config(self, dependency_manager: DependencyManager):
        self.config = ConfigManager(self.folder)
        self.config.check_dependencies(dependency_manager)

    def dicom_folder(self):
        return os.path.join(self.folder, self.global_config.get_default_dicom_folder())

    def check_pt_folder(self, pt_folder: str):
        if not os.path.exists(pt_folder):
            return PatientRet.FolderNotFound

        if ' ' in pt_folder:
            return PatientRet.PathBlankSpaces

        if not os.path.abspath(pt_folder).startswith(os.path.abspath(self.global_config.get_patients_folder() + os.sep)):
            return PatientRet.FolderOutsideMain

        if not self.check_pt_dir(pt_folder):
            return PatientRet.InvalidFolderTree

        return PatientRet.ValidFolder

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
        try:
            src_path = os.path.join(self.dicom_folder(), str(data_input))

            shutil.rmtree(src_path, ignore_errors=True)
            os.makedirs(src_path, exist_ok=True)

            # Reset the workflows related to the deleted DICOM images
            src_path = os.path.join(self.folder, self.name + strings.WF_DIR_SUFFIX,
                                    data_input.value.wf_name)
            shutil.rmtree(src_path, ignore_errors=True)
            return True
        except:
            return False

    def check_pt_dir(self, pt_folder: str) -> bool:
        """
        Check if a directory is a valid patient folder

        Parameters
        ----------
        pt_folder : str
            The directory path to check.

        Returns
        -------
        bool
            True if the directory is a valid patient folder, otherwise False.

        """

        for data_input in DataInputList:
            if not os.path.exists(os.path.join(pt_folder, self.global_config.get_default_dicom_folder(), str(data_input))):
                return False

        return True

    def update_pt_dir(self, pt_folder: str):
        """
        Update an existing folder with the patient subfolder structure.

        Parameters
        ----------
        pt_folder : str
            The directory path to update into a patient folder.

        Returns
        -------
        None.

        """

        for data_input in DataInputList:
            if not os.path.exists(
                    os.path.join(pt_folder, self.global_config.get_default_dicom_folder(), str(data_input))):
                os.makedirs(os.path.join(pt_folder, self.global_config.get_default_dicom_folder(), str(data_input)),
                            exist_ok=True)

    def create_new_pt_dir(self, pt_name: str) -> bool:
        """
        Create a new patient folder and subfolders.

        Parameters
        ----------
        pt_name : str
            The patient folder name.

        Returns
        -------
        True if no Exception raised.

        """

        try:
            base_folder = os.path.abspath(os.path.join(
                self.global_config.get_patients_folder(), pt_name))

            dicom_folder = os.path.join(base_folder, self.global_config.get_default_dicom_folder())
            for data_input in DataInputList:
                os.makedirs(os.path.join(
                    dicom_folder, str(data_input)), exist_ok=True)
            if self.load(base_folder) == PatientRet.ValidFolder:
                return True
            else:
                return False
        except:
            return False




