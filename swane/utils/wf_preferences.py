import os
from swane.utils.DataInput import DataInputList
from swane.utils.PreferenceEntry import PreferenceEntry

wf_preferences = {}

category = DataInputList.T13D
wf_preferences[category] = {}
wf_preferences[category]['bet_bias_correction'] = {
    'input_type': PreferenceEntry.CHECKBOX,
    'label': "Bias reduction for skull removal",
    'tooltip': "Increase time with better results",
    'default': 'false',
}
wf_preferences[category]['bet_thr'] = {
    'input_type': PreferenceEntry.FLOAT,
    'label': "Threshold value for skull removal",
    'default': 0.3,
    'range': [0, 1],
}
wf_preferences[category]['freesurfer'] = {
    'input_type': PreferenceEntry.CHECKBOX,
    'label': "FreeSurfer analysis",
    'default': 'true',
    'dependency': 'is_freesurfer',
    'dependency_fail_tooltip': "Freesurfer not detected",
}
wf_preferences[category]['hippo_amyg_labels'] = {
    'input_type': PreferenceEntry.CHECKBOX,
    'label': "FreeSurfer hippocampal subfields",
    'default': 'false',
    'dependency': 'is_freesurfer_matlab',
    'dependency_fail_tooltip': "Matlab Runtime not detected",
    'pref_requirement': {DataInputList.T13D: ['freesurfer']},
    'pref_requirement_fail_tooltip': "Requires Freesurfer analysis",
}
wf_preferences[category]['flat1'] = {
    'input_type': PreferenceEntry.CHECKBOX,
    'label': "FLAT1 analysis",
    'default': 'true',
    'input_requirement': [DataInputList.FLAIR3D],
    'input_requirement_fail_tooltip': "Requires both 3D T1w and 3D Flair",
}

category = DataInputList.FLAIR3D
wf_preferences[category] = {}
wf_preferences[category]['bet_bias_correction'] = wf_preferences[DataInputList.T13D]['bet_bias_correction']
wf_preferences[category]['bet_thr'] = wf_preferences[DataInputList.T13D]['bet_thr']

category = DataInputList.MDC
wf_preferences[category] = {}
wf_preferences[category]['bet_bias_correction'] = wf_preferences[DataInputList.T13D]['bet_bias_correction']
wf_preferences[category]['bet_thr'] = wf_preferences[DataInputList.T13D]['bet_thr']

category = DataInputList.VENOUS
wf_preferences[category] = {}
wf_preferences[category]['bet_bias_correction'] = wf_preferences[DataInputList.T13D]['bet_bias_correction']
wf_preferences[category]['bet_thr'] = wf_preferences[DataInputList.T13D]['bet_thr']
wf_preferences[category]['veindetectionmode'] = {
    'input_type': PreferenceEntry.COMBO,
    'label': "Venous volume detection mode",
    'default': ['Automatic (standard deviation)', 'Automatic (mean value)', 'Always first volume', 'Always second volume'],
}

category = DataInputList.ASL
wf_preferences[category] = {}
wf_preferences[category]['ai'] = {
    'input_type': PreferenceEntry.CHECKBOX,
    'label': "Asymmetry Index map for ASL",
    'default': 'true',
    'pref_requirement': {DataInputList.T13D: ['freesurfer']},
    'pref_requirement_fail_tooltip': "Requires Freesurfer analysis",
}

wf_preferences[DataInputList.PET] = wf_preferences[DataInputList.ASL]

category = DataInputList.DTI
wf_preferences[category] = {}
wf_preferences[category]['tractography'] = {
    'input_type': PreferenceEntry.CHECKBOX,
    'label': "DTI tractography",
    'default': 'true',
}

try:
    XTRACT_DATA_DIR = os.path.abspath(os.path.join(os.environ["FSLDIR"], "data/xtract_data/Human"))
except:
    XTRACT_DATA_DIR = ""
DEFAULT_N_SAMPLES = 5000

TRACTS = {"af": ['Arcuate Fasciculus', 'true', 0],
          "ar": ['Acoustic Radiation', 'false', 0],
          "atr": ['Anterior Thalamic Radiation', 'false', 0],
          "cbd": ['Cingulum subsection : Dorsal', 'false', 0],
          "cbp": ['Cingulum subsection : Peri-genual', 'false', 0],
          "cbt": ['Cingulum subsection : Temporal', 'false', 0],
          "cst": ['Corticospinal Tract', 'true', 0],
          "fa": ['Frontal Aslant', 'false', 0],
          "fma": ['Forceps Major', 'false', 0],
          "fmi": ['Forceps Minor', 'false', 0],
          "fx": ['Fornix', 'false', 0],
          "ilf": ['Inferior Longitudinal Fasciculus', 'false', 0],
          "ifo": ['Inferior Fronto-Occipital Fasciculus', 'false', 0],
          "mcp": ['Middle Cerebellar Peduncle', 'false', 0],
          "mdlf": ['Middle Longitudinal Fasciculus', 'false', 0],
          "or": ['Optic Radiation', 'true', 0],
          "str": ['Superior Thalamic Radiation', 'false', 0],
          "ac": ['Anterior Commissure', 'false', 0],
          "uf": ['Uncinate Fasciculus', 'false', 0],
          "vof": ['Vertical Occipital Fasciculus', 'false', 0],
          }
structure_file = os.path.join(XTRACT_DATA_DIR, "structureList")
if os.path.exists(structure_file):
    with open(structure_file, 'r') as file:
        for line in file.readlines():
            split = line.split(" ")
            tract_name = split[0][:-2]
            if tract_name in tuple(TRACTS.keys()):
                try:
                    TRACTS[tract_name][2] = int(float(split[1])*1000)
                except:
                    TRACTS[tract_name][2] = DEFAULT_N_SAMPLES

for k in list(TRACTS.keys()):
    if TRACTS[k][2] == 0:
        del TRACTS[k]

for tract in TRACTS.keys():
    wf_preferences[category][tract] = {
        'input_type': PreferenceEntry.CHECKBOX,
        'label': TRACTS[tract][0],
        'default': TRACTS[tract][0],
        'pref_requirement': {DataInputList.DTI: ['tractography']},
        'pref_requirement_fail_tooltip': "Tractography disabled",
    }


category = DataInputList.FMRI+"_0"
wf_preferences[category] = {}
wf_preferences[category]['task_a_name'] = {
    'input_type': PreferenceEntry.TEXT,
    'label': "Task A name",
    'default': "Task A",
}
wf_preferences[category]['task_b_name'] = {
    'input_type': PreferenceEntry.TEXT,
    'label': "Task B name",
    'default': "Task B",
}
wf_preferences[category]['task_duration'] = {
    'input_type': PreferenceEntry.NUMBER,
    'label': "Tasks duration (sec)",
    'default': "30",
    'range': [1, 500],
}
wf_preferences[category]['rest_duration'] = {
    'input_type': PreferenceEntry.NUMBER,
    'label': "Rest duration (sec)",
    'default': "30",
    'range': [1, 500],
}
wf_preferences[category]['tr'] = {
    'input_type': PreferenceEntry.TEXT,
    'label': "Repetition Time (TR)",
    'default': "auto",
}
wf_preferences[category]['vols'] = {
    'input_type': PreferenceEntry.TEXT,
    'label': "Task B duration",
    'default': "auto",
}
wf_preferences[category]['slicetiming'] = {
    'input_type': PreferenceEntry.COMBO,
    'label': "Slice timing",
    'default': ['Unknown', 'Regular up', 'Regular down', 'Interleaved'],
}
wf_preferences[category]['blockdesign'] = {
    'input_type': PreferenceEntry.COMBO,
    'label': "Block design",
    'default': ['rArA...', 'rArBrArB...'],
}
wf_preferences[category]['del_start_vols'] = {
    'input_type': PreferenceEntry.NUMBER,
    'label': "Delete start volumes",
    'default': "0",
    'range': [1, 500],
}
wf_preferences[category]['del_end_vols'] = {
    'input_type': PreferenceEntry.NUMBER,
    'label': "Delete end volumes",
    'default': "0",
    'range': [1, 500],
}

wf_preferences[DataInputList.FMRI+"_1"] = wf_preferences[DataInputList.FMRI+"_0"]
wf_preferences[DataInputList.FMRI+"_2"] = wf_preferences[DataInputList.FMRI+"_0"]
