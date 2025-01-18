from enum import Enum, auto

from swane.config.PrefCategory import PrefCategory


class InputTypes(Enum):
    TEXT = auto()
    PASSWORD = auto()
    INT = auto()
    BOOLEAN = auto()
    ENUM = auto()
    FILE = auto()
    DIRECTORY = auto()
    FLOAT = auto()

class WORKFLOW_TYPES(Enum):
    STRUCTURAL = "Structural Workflow"
    FUNCTIONAL = "Morpho-Functional Workflow"

class SLICER_EXTENSIONS(Enum):
    MRB = "mrb"
    MRML = "mrml"

class CORE_LIMIT(Enum):
    NO_LIMIT = "No limit"
    SOFT_CAP = "Soft cap"
    HARD_CAP = "Hard Cap"

class BETWEEN_MOD_FLIRT_COST(Enum):
    MULTUAL_INFORMATION = "Mutual information"
    NORMALIZED_MUTUAL_INFORMATION = "Normalized mutual information"
    CORRELATION_RATIO = "Correlation ratio"

class VEIN_DETECTION_MODE(Enum):
    SD = 'Automatic (standard deviation)'
    MEAN = 'Automatic (mean value)'
    FIRST = 'Always first volume'
    SECOND = 'Always second volume'

class BLOCK_DESIGN(Enum):
    RARA = 'rArA...'
    RARB = 'rArBrArB...'

class SLICE_TIMING(Enum):
    UNKNOWN = 'Unknown'
    UP = 'Regular up'
    DOWN = 'Regular down'
    INTERLEAVED = 'Interleaved'

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


class GlobalPrefCategoryList(Enum):
    MAIN = PrefCategory("main", "Global settings")
    PERFORMANCE = PrefCategory("performance", 'Performance')
    OPTIONAL_SERIES = PrefCategory("optional_series", 'Optional series')
    MAIL_SETTINGS = PrefCategory("mail_settings", "Mail settings")

    def __str__(self):
        return self.value.name
