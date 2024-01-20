from swane.config.model.PreferenceEntry import PreferenceEntry
from swane.config.model.BoolPreferenceEntry import BoolPreferenceEntry
from swane.config.model.EnumPreference import WORKFLOW_TYPES
from swane.utils.DataInputList import DataInputList


class T13DPreference:
    
    wf_type: PreferenceEntry = PreferenceEntry(
        input_type=InputTypes.ENUM,
        hidden=True,
        label="Default workflow",
        value_enum=WORKFLOW_TYPES,
        default=WORKFLOW_TYPES.STRUCTURAL,
    )
    bet_bias_correction = BoolPreferenceEntry(
        label="Bias reduction for skull removal",
        tooltip="Increase time with better results",
        default='false',
    )
    bet_thr = PreferenceEntry(
        input_type=InputTypes.FLOAT,
        label="Threshold value for skull removal",
        default=0.3,
        tooltip="Accepted values from 0 to 1, higher values are considered equal 1",
        range=[0, 1],
    )
    freesurfer = BoolPreferenceEntry(
        label="FreeSurfer analysis",
        default='true',
        dependency='is_freesurfer',
        dependency_fail_tooltip="Freesurfer not detected",
    )
    hippo_amyg_labels = BoolPreferenceEntry(
        label="FreeSurfer hippocampal and amygdala subfields",
        default='false',
        dependency='is_freesurfer_matlab',
        dependency_fail_tooltip="Matlab Runtime not detected",
        pref_requirement={DataInputList.T13D: [('freesurfer', True)]},
        pref_requirement_fail_tooltip="Requires Freesurfer analysis",
    )
    flat1 = BoolPreferenceEntry(
        label="FLAT1 analysis",
        default='true',
        input_requirement=[DataInputList.FLAIR3D],
        input_requirement_fail_tooltip="Requires both 3D T1w and 3D Flair",
    )
