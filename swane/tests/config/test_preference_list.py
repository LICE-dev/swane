from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.config.config_enums import (
    GlobalPrefCategoryList,
    SegmentationEngine,
    InputTypes,
)


def test_segmentation_engine_pref_registered_ants_default():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["segmentation_engine"]
    assert entry.input_type == InputTypes.ENUM
    assert entry.value_enum is SegmentationEngine
    assert entry.default is SegmentationEngine.ANTS


def test_segmentation_engine_ants_option_gated_on_antspyx():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["segmentation_engine"]
    dep = entry.option_dependency[SegmentationEngine.ANTS]
    assert dep[0] == "is_antspyx"
    # FSL FAST needs no antspyx gate
    assert SegmentationEngine.FSL not in entry.option_dependency
