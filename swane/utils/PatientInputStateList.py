import os

from swane.utils.DataInputList import DataInputList
from swane.utils.PatientInputState import PatientInputState


class PatientInputStateList(dict):

    def __init__(self, dicom_dir=None):
        super().__init__()
        self.dicom_dir = dicom_dir
        for data_input in DataInputList:
            self[data_input] = PatientInputState()

    def is_ref_loaded(self):
        return self[DataInputList.T13D].loaded

    def get_dicom_dir(self, data_input: DataInputList):
        return os.path.join(self.dicom_dir, str(data_input))
