from swane.config.config_enums import InputTypes
from enum import Enum

class PreferenceEntry:
    """
    Contains information to manage loading, saving and visualization of a preference
    """

    input_type = InputTypes.TEXT
    label = ""
    default = None
    tooltip = ""
    range = None
    decimals = None
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
    value_enum = None
    default_at_startup = False

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key) and PreferenceEntry.check_type(key, value):
                setattr(self, key, value)

    @staticmethod
    def check_type(key, value):
        types = {
                'input_type': InputTypes,
                "label": str,
                "tooltip": str,
                "range": list,
                "decimals": int,
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
                #"value_enum": Enum
        }
        if key in types:
            if types[key] == Enum:
                return isinstance(value, Enum)
            return type(value) is types[key]
        return True



