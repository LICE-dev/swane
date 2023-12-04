import os
from swane.utils.DataInputList import DataInputList
from enum import Enum, auto
from swane.config.ConfigManager import ConfigManager
from swane.utils.PatientInputStateList import PatientInputStateList


class PatientRet(Enum):
    FolderNotFound = auto()
    PathBlankSpaces = auto()
    FolderOutsideMain = auto()
    InvalidFolderTree = auto()
    ValidFolder = auto()


class Patient:

    def __init__(self, global_config: ConfigManager):
        self.folder = None
        self.name = None
        self.global_config = global_config
        self.input_state_list = None

    def load(self, pt_folder: str) -> PatientRet:
        check = self.check_pt_folder(pt_folder)
        if check == PatientRet.ValidFolder:
            self.folder = pt_folder
            self.name = os.path.basename(pt_folder)
            self.input_state_list = PatientInputStateList(self.dicom_folder(), self.global_config)
        return check

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




