import typing
from swane.config.model.T13DPreference import T13DPreference
from swane.utils.DataInputList import DataInputList
from typing import Literal

PreferenceListDeclaration = {
    "DataInputList.T13D": T13DPreference
}


class PreferenceList(dict):

    @typing.overload
    def __getitem__(self, name: Literal[DataInputList.T13D]) -> T13DPreference: ...

    def __getitem__(self, name):
        return super().__getitem__(name)

    def __init__(self):
        super().__init__()
        self[DataInputList.T13D]: T13DPreference = T13DPreference()


PreferenceList()[DataInputList.T13D]