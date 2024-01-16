from abc import ABC, abstractmethod
from enum import Enum

class PreferenceEntry(ABC):
    value = None
    label = ""
    default = None
    tooltip = ""
    range = None
    dependency = None
    dependency_fail_tooltip = None
    pref_requirement = None
    pref_requirement_fail_tooltip = None
    input_requirement = None
    input_requirement_fail_tooltip = None
    restart = False
    validate_on_change = False
    informative_text: dict = None
    box_text = None
    hidden = False
    
    types = {
                "label": str,
                "tooltip": str,
                "range": list,
                "dependency": str,
                "dependency_fail_tooltip": str,
                "pref_requirement": dict,
                "pref_requirement_fail_tooltip": str,
                "input_requirement": list,
                "input_requirement_fail_tooltip": str,
                "restart": bool,
                "validate_on_change": bool,
                "informative_text": dict,
                "box_text": str,
                "hidden": bool,
        }
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key) and self.check_type(key, value):
                setattr(self, key, value)

    def check_type(self, key, value):
        if key in self.types:
            if self.types[key] == Enum:
                return isinstance(value, Enum)
            return type(value) is self.types[key]
        return True
    
    def set_value(self, value: object):
        raise Exception