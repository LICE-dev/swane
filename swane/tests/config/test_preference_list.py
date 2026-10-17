from swane.config import dependency_policy
from swane.config.dependency_policy import default_engines
from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.config.config_enums import (
    GlobalPrefCategoryList,
    SegmentationEngine,
    InputTypes,
)


def test_segmentation_engine_pref_registered_with_policy_default():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["segmentation_engine"]
    assert entry.input_type == InputTypes.ENUM
    assert entry.value_enum is SegmentationEngine
    assert (
        entry.default
        is default_engines(dependency_policy.FSL_MANDATORY)["segmentation_engine"]
    )


def test_segmentation_engine_ants_option_gated_on_antspyx():
    entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["segmentation_engine"]
    dep = entry.option_dependency[SegmentationEngine.ANTS]
    assert dep[0] == "is_antspyx"
    # FSL is only a recommended dependency: FAST is gated on FSL itself
    assert entry.option_dependency[SegmentationEngine.FSL][0] == "is_fsl"
