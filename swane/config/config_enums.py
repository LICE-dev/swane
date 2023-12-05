from enum import IntEnum, StrEnum, Enum


class InputTypes(IntEnum):
    TEXT = 0
    NUMBER = 1
    CHECKBOX = 2
    COMBO = 3
    FILE = 4
    DIRECTORY = 5
    FLOAT = 6
    HIDDEN = 7


class ImageModality(Enum):
    RM = 'mr'
    PET = 'pt'

    @staticmethod
    def from_string(mod_string: str):
        for mod in ImageModality:
            if mod.value.lower() == mod_string.lower():
                return mod
        return None


class PLANES(Enum):
    TRA = 'transverse'
    COR = 'coronal'
    SAG = 'sagittal'
