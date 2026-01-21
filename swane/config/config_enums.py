from enum import Enum, auto

from swane import strings
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


class WorkflowTypes(Enum):
    STRUCTURAL = "Structural Workflow"
    FUNCTIONAL = "Morpho-Functional Workflow"


class SlicerExtensions(Enum):
    MRB = "mrb"
    MRML = "mrml"


class CoreLimit(Enum):
    NO_LIMIT = "No limit"
    SOFT_CAP = "Soft cap"
    HARD_CAP = "Hard Cap"


class BetweenModFlirtCost(Enum):
    MULTUAL_INFORMATION = "Mutual information"
    NORMALIZED_MUTUAL_INFORMATION = "Normalized mutual information"
    CORRELATION_RATIO = "Correlation ratio"


class VeinDetectionMode(Enum):
    SD = "Automatic (standard deviation)"
    MEAN = "Automatic (mean value)"
    FIRST = "Always first volume"
    SECOND = "Always second volume"


class BlockDesign(Enum):
    RARA = "rArA..."
    RARB = "rArBrArB..."


class FreesurferStep(Enum):
    DISABLED = "Disabled"
    SYNTHSEG = "SynthSeg Cortical Parcellation only (if available)"
    AUTORECON2 = "Preprocessing only"
    AUTORECON_PIAL = "Surfaces + Cortical Parcellation"
    RECONALL = "Complete Recon-all"

    def has_surface(self):
        return self in {FreesurferStep.AUTORECON_PIAL, FreesurferStep.RECONALL}

    def has_parcellation(self):
        return self in {
            FreesurferStep.SYNTHSEG,
            FreesurferStep.AUTORECON_PIAL,
            FreesurferStep.RECONALL,
        }


class SliceTiming(Enum):
    UNKNOWN = "Unknown"
    UP = "Regular up"
    DOWN = "Regular down"
    INTERLEAVED = "Interleaved"


class ImageModality(Enum):
    RM = "mr"
    PET = "pt"
    CT = "ct"
    XA = "xa"

    @staticmethod
    def from_string(mod_string: str):
        for mod in ImageModality:
            if mod.value.lower() == mod_string.lower():
                return mod
        return None


class Planes(Enum):
    TRA = "transverse"
    COR = "coronal"
    SAG = "sagittal"


class GlobalPrefCategoryList(Enum):
    MAIN = PrefCategory("main", "Global settings")
    PERFORMANCE = PrefCategory("performance", "Performance")
    SYNTH = PrefCategory("synth", "Synth tools")
    OPTIONAL_SERIES = PrefCategory("optional_series", "Optional series")
    MAIL_SETTINGS = PrefCategory("mail_settings", "Mail settings")

    def __str__(self):
        return self.value.name


class PerformanceProfile(str, Enum):
    """
    Enumeration of performance profiles selectable in the configuration wizard.

    Each value represents a user-facing profile that SWANe can use to balance
    performance and resource usage.

    Notes
    -----
    The enum values are localized strings from `swane.strings`.

    """

    MAX_PERF = strings.performance_profile_max
    BALANCED = strings.performance_profile_balanced
    LOW_RESOURCE = strings.performance_profile_min
