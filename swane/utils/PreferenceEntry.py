from enum import IntEnum


class InputTypes(IntEnum):
    TEXT = 0
    NUMBER = 1
    CHECKBOX = 2
    COMBO = 3
    FILE = 4
    DIRECTORY = 5
    FLOAT = 6
    HIDDEN = 7


class PreferenceEntry:
    input_type = InputTypes.TEXT
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
    informative_text = None
    box_text = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


