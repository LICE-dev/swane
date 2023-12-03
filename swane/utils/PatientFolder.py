import os
from swane.utils.DataInputList import DataInputList
from enum import Enum, auto


class PatientRet(Enum):
    FolderNotFound = auto()
    PathBlankSpaces = auto()
    FolderOutsideMain = auto()
    InvalidFolderTree = auto()
    ValidFolder = auto()


class PatientFolder:

    def __init__(self, main_working_directory: str, default_dicom_folder: str):
        self.pt_folder = None
        self.pt_name = None
        self.main_working_directory = main_working_directory
        self.default_dicom_folder = default_dicom_folder

    def load(self, pt_folder) -> PatientRet:
        check = self.check_pt_folder(pt_folder)
        if check == PatientRet.ValidFolder:
            self.pt_folder = pt_folder
        return check

    def check_pt_folder(self, pt_folder: str):
        print(pt_folder)
        if not os.path.exists(pt_folder):
            return PatientRet.FolderNotFound

        if ' ' in pt_folder:
            return PatientRet.PathBlankSpaces

        if not os.path.abspath(pt_folder).startswith(os.path.abspath(self.main_working_directory + os.sep)):
            return PatientRet.FolderOutsideMain

        if not self.check_pt_dir(pt_folder):
            return PatientRet.InvalidFolderTree

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
            if not os.path.exists(os.path.join(pt_folder, self.default_dicom_folder, str(data_input))):
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
                    os.path.join(pt_folder, self.default_dicom_folder, str(data_input))):
                os.makedirs(os.path.join(pt_folder, self.default_dicom_folder, str(data_input)),
                            exist_ok=True)



