import os
from swane.config.ConfigManager import ConfigManager
from swane.utils.DataInputList import DataInputList


class SubjectInputState:
    def __init__(self):
        self.loaded = False
        self.volumes = 0


class SubjectInputStateList(dict[DataInputList, SubjectInputState]):
    def __init__(self, dicom_dir: str, global_config: ConfigManager):
        super().__init__()
        self.dicom_dir = dicom_dir
        for data_input in DataInputList:
            if data_input.value.optional and not global_config.is_optional_series_enabled(data_input):
                continue
            self[data_input] = SubjectInputState()

    def is_ref_loaded(self):
        return self[DataInputList.T13D].loaded

    def get_dicom_dir(self, data_input: DataInputList):
        return os.path.join(self.dicom_dir, str(data_input))



