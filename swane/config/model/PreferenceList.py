from typing import Any
from swane.config.model.T13DPreference import GenericPreference, T13DPreference
from swane.utils.DataInputList import DataInputList

class PreferenceList():
        
    T13D: T13DPreference = T13DPreference()
    
    def __init__(self) -> None:
        pass
    
    def get_typed_attr(self, data_type: DataInputList) -> GenericPreference:
        
        return getattr(self, data_type.name)
        
    
        
preference = PreferenceList()
asd = preference.get_typed_attr(DataInputList.T13D)