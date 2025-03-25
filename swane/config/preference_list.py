import os
from swane.utils.DataInputList import DataInputList, FMRI_NUM
from swane import __version__
from multiprocessing import cpu_count
from nipype.utils.profiler import get_system_total_memory_gb
from math import ceil

from swane import strings
from swane.config.PreferenceEntry import PreferenceEntry
from swane.config.config_enums import (InputTypes, WORKFLOW_TYPES, SLICER_EXTENSIONS, CORE_LIMIT, VEIN_DETECTION_MODE,
                                       BLOCK_DESIGN, SLICE_TIMING, GlobalPrefCategoryList, BETWEEN_MOD_FLIRT_COST)

try:
    base_dir = os.path.abspath(os.path.join(os.environ["FSLDIR"], "data/xtract_data"))
    human_path = os.path.join(base_dir, "Human")
    HUMAN_path = os.path.join(base_dir, "HUMAN")

    if os.path.exists(human_path):
        # For FSL Version < 6.0.7
        XTRACT_DATA_DIR = human_path
    elif os.path.exists(HUMAN_path):
        # For FSL Version >= 6.0.7
        XTRACT_DATA_DIR = HUMAN_path
    else:
        XTRACT_DATA_DIR = ""
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
structure_file=os.path.join(XTRACT_DATA_DIR, "structureList")
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

# WORKFLOW_TYPES = ["Structural Workflow", "Morpho-Functional Workflow"]
# SLICER_EXTENSIONS = ["mrb", "mrml"]

# WORKFLOWS PREFERENCE LIST
WF_PREFERENCES = {}

category = DataInputList.T13D
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['wf_type'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    hidden=True,
    label="Default workflow",
    value_enum=WORKFLOW_TYPES,
    default=WORKFLOW_TYPES.STRUCTURAL,
)
WF_PREFERENCES[category]['bet_bias_correction'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Bias reduction for skull removal",
    tooltip="Increase time with better results",
    default='false',
)
WF_PREFERENCES[category]['bet_thr'] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="Threshold value for skull removal",
    default=0.3,
    tooltip="Accepted values from 0 to 1, higher values are considered equal 1",
    range=[0, 1],
)
WF_PREFERENCES[category]['freesurfer'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="FreeSurfer analysis",
    default='true',
    dependency='is_freesurfer',
    dependency_fail_tooltip="Freesurfer not detected",
)
WF_PREFERENCES[category]['hippo_amyg_labels'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="FreeSurfer hippocampal and amygdala subfields",
    default='false',
    dependency='is_freesurfer_matlab',
    dependency_fail_tooltip="Matlab Runtime not detected",
    pref_requirement={DataInputList.T13D: [('freesurfer', True)]},
    pref_requirement_fail_tooltip="Requires Freesurfer analysis",
)
WF_PREFERENCES[category]['flat1'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="FLAT1 analysis",
    default='true',
    input_requirement=[DataInputList.FLAIR3D],
    input_requirement_fail_tooltip="Requires both 3D T1w and 3D Flair",
)

category = DataInputList.FLAIR3D
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['bet_bias_correction']=WF_PREFERENCES[DataInputList.T13D]['bet_bias_correction']
WF_PREFERENCES[category]['bet_thr'] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="Threshold value for skull removal",
    default=0.5,
    tooltip="Accepted values from 0 to 1, higher values are considered equal 1",
    range=[0, 1],
)

category = DataInputList.MDC
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['bet_bias_correction']=WF_PREFERENCES[DataInputList.T13D]['bet_bias_correction']
WF_PREFERENCES[category]['bet_thr'] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="Threshold value for skull removal",
    default=0.5,
    tooltip="Accepted values from 0 to 1, higher values are considered equal 1",
    range=[0, 1],
)

category = DataInputList.VENOUS
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['bet_thr'] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="Threshold value for skull removal",
    default=0.4,
    tooltip="Accepted values from 0 to 1, higher values are considered equal 1",
    range=[0, 1],
)
WF_PREFERENCES[category]['vein_detection_mode'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="Venous volume detection mode",
    value_enum=VEIN_DETECTION_MODE,
    default=VEIN_DETECTION_MODE.SD,
)
WF_PREFERENCES[category]['vein_segment_threshold'] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="Threshold (%) for 3DSlicer Vein Segment",
    default=97.5,
    range=[0.1, 100],
    decimals=1
)

category = DataInputList.ASL
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['cost_func'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="FLIRT between modalities cost function",
    value_enum=BETWEEN_MOD_FLIRT_COST,
    default=BETWEEN_MOD_FLIRT_COST.NORMALIZED_MUTUAL_INFORMATION,
)
WF_PREFERENCES[category]['ai'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Asymmetry Index map for ASL",
    default='true',
)
WF_PREFERENCES[category]['ai_threshold'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="Threshold for Asymmetry Index map outliers removal",
    tooltip="100 for no thresholding, suggested 80-90",
    default=85,
    range=[0, 100],
    pref_requirement={DataInputList.ASL: [('ai', True)]},
    pref_requirement_fail_tooltip="Requires ASL Asymmetry Index",
)

category = DataInputList.PET
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['cost_func'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="FLIRT between modalities cost function",
    value_enum=BETWEEN_MOD_FLIRT_COST,
    default=BETWEEN_MOD_FLIRT_COST.MULTUAL_INFORMATION,
)
WF_PREFERENCES[category]['ai'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Asymmetry Index map for PET",
    default='true',
)
WF_PREFERENCES[category]['ai_threshold'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="Threshold for Asymmetry Index map outliers removal",
    tooltip="100 for no thresholding, suggested 80-90",
    default=85,
    range=[0, 100],
    pref_requirement={DataInputList.PET: [('ai', True)]},
    pref_requirement_fail_tooltip="Requires PET Asymmetry Index",
)
category = DataInputList.DTI
WF_PREFERENCES[category] = {}
WF_PREFERENCES[category]['old_eddy_correct'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Use older but faster fsl eddy_correct",
    default='false',
)
WF_PREFERENCES[category]['tractography'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="DTI tractography",
    default='true',
)
WF_PREFERENCES[category]['tractography_threshold'] = PreferenceEntry(
    input_type=InputTypes.FLOAT,
    label="Threshold for 3DSlicer DTI Tract",
    tooltip="This value is multiplied by the tract waytotal for threshold calculation",
    default=0.0035,
    range=[0.0001, 1],
    decimals=4
)
WF_PREFERENCES[category]['track_procs'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="Parallel processes for each side tractography",
    default=5,
    range=[1, 10],
    pref_requirement={DataInputList.DTI: [('tractography', True)]},
    pref_requirement_fail_tooltip="Tractography disabled",
)

for tract in TRACTS.keys():
    WF_PREFERENCES[category][tract] = PreferenceEntry(
        input_type=InputTypes.BOOLEAN,
        label=TRACTS[tract][0],
        default=TRACTS[tract][1],
        pref_requirement={DataInputList.DTI: [('tractography', True)]},
        pref_requirement_fail_tooltip="Tractography disabled",
    )

for x in range(FMRI_NUM):
    category = DataInputList['FMRI'+"_%s" % x]
    WF_PREFERENCES[category] = {}
    WF_PREFERENCES[category]['task_a_name'] = PreferenceEntry(
        input_type=InputTypes.TEXT,
        label="Task A name",
        default="Task_A",
    )
    WF_PREFERENCES[category]['block_design'] = PreferenceEntry(
        input_type=InputTypes.ENUM,
        label="Block design",
        value_enum=BLOCK_DESIGN,
        default=BLOCK_DESIGN.RARA,
    )
    WF_PREFERENCES[category]['task_b_name'] = PreferenceEntry(
        input_type=InputTypes.TEXT,
        label="Task B name",
        default="Task_B",
        pref_requirement={DataInputList['FMRI'+"_%s" % x]: [('block_design', BLOCK_DESIGN.RARB)]},
        pref_requirement_fail_tooltip="Requires rArBrArB... block design",
    )
    WF_PREFERENCES[category]['task_duration'] = PreferenceEntry(
        input_type=InputTypes.INT,
        label="Tasks duration (sec)",
        default=30,
        range=[1, 500],
    )
    WF_PREFERENCES[category]['rest_duration'] = PreferenceEntry(
        input_type=InputTypes.INT,
        label="Rest duration (sec)",
        default=30,
        range=[0, 500],
    )
    WF_PREFERENCES[category]['tr'] = PreferenceEntry(
        input_type=InputTypes.FLOAT,
        label="Repetition Time (TR)",
        tooltip="Set -1 for automatic detection",
        default="-1.0",
        range=[-1, 1000],
    )
    WF_PREFERENCES[category]['n_vols'] = PreferenceEntry(
        input_type=InputTypes.INT,
        label="Number of volumes",
        tooltip="Set -1 for automatic detection",
        default="-1",
        range=[-1, 1000],
    )
    WF_PREFERENCES[category]['slice_timing'] = PreferenceEntry(
        input_type=InputTypes.ENUM,
        label="Slice timing",
        value_enum=SLICE_TIMING,
        default=SLICE_TIMING.UNKNOWN,
    )
    WF_PREFERENCES[category]['del_start_vols'] = PreferenceEntry(
        input_type=InputTypes.INT,
        label="Delete start volumes",
        default=0,
        range=[1, 500],
    )
    WF_PREFERENCES[category]['del_end_vols'] = PreferenceEntry(
        input_type=InputTypes.INT,
        label="Delete end volumes",
        default=0,
        range=[1, 500],
    )

GLOBAL_PREFERENCES = {}

category = GlobalPrefCategoryList.MAIN
GLOBAL_PREFERENCES[category] = {}
GLOBAL_PREFERENCES[category]['main_working_directory'] = PreferenceEntry(
    input_type=InputTypes.DIRECTORY,
    label="Main working directory",
    box_text='Select the main working directory',
    default="",
    restart=True
)
GLOBAL_PREFERENCES[category]['subjects_prefix'] = PreferenceEntry(
    input_type=InputTypes.TEXT,
    hidden=True,
    default="subj_",
)
GLOBAL_PREFERENCES[category]['slicer_path'] = PreferenceEntry(
    input_type=InputTypes.FILE,
    label="3D Slicer path",
    box_text="Select 3D Slicer executable",
    default="",
    restart=True,
    validate_on_change=True
)
GLOBAL_PREFERENCES[category]['slicer_version'] = PreferenceEntry(
    input_type=InputTypes.TEXT,
    hidden=True,
    default="",
)
GLOBAL_PREFERENCES[category]['last_pid'] = PreferenceEntry(
    input_type=InputTypes.INT,
    hidden=True,
    default=-1,
)
GLOBAL_PREFERENCES[category]['last_swane_version'] = PreferenceEntry(
    input_type=InputTypes.TEXT,
    hidden=True,
    default=__version__,
)
GLOBAL_PREFERENCES[category]['force_pref_reset'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    hidden=True,
    default="false",
)
GLOBAL_PREFERENCES[category]['slicer_scene_ext'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    hidden=True,
    value_enum=SLICER_EXTENSIONS,
    default=SLICER_EXTENSIONS.MRB,
)
GLOBAL_PREFERENCES[category]['default_dicom_folder'] = PreferenceEntry(
    input_type=InputTypes.TEXT,
    hidden=True,
    default="dicom",
)
GLOBAL_PREFERENCES[category]['default_wf_type'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="Default workflow",
    value_enum=WORKFLOW_TYPES,
    default=WORKFLOW_TYPES.STRUCTURAL,
)
GLOBAL_PREFERENCES[category]['shutdown'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    hidden=True,
    label=strings.menu_shutdown_pref,
    default='false',
    default_at_startup='true',
)
category = GlobalPrefCategoryList.PERFORMANCE
GLOBAL_PREFERENCES[category] = {}
GLOBAL_PREFERENCES[category]['max_subj'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="Patient tab limit",
    default=1,
    range=[0, 5],
)
try:
    suggested_max_cpu = max(ceil(min(cpu_count()/2, get_system_total_memory_gb()/3)), 1)
except:
    suggested_max_cpu = 1
GLOBAL_PREFERENCES[category]['max_subj_cu'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="CPU core limit per subject",
    tooltip="To use all CPU cores set value equal to -1",
    default=str(suggested_max_cpu),
    range=[-1, 30],
)
GLOBAL_PREFERENCES[category]['resource_monitor'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Enable resource monitor",
    default='false',
)
GLOBAL_PREFERENCES[category]['multicore_node_limit'] = PreferenceEntry(
    input_type=InputTypes.ENUM,
    label="CPU management for multi-core steps",
    value_enum=CORE_LIMIT,
    default=CORE_LIMIT.SOFT_CAP,
    informative_text={
        CORE_LIMIT.NO_LIMIT: "Multi-core steps ignore the subject CPU core limit, using all available resources",
        CORE_LIMIT.SOFT_CAP: "Multi-core steps use up to twice the subject CPU core limit",
        CORE_LIMIT.HARD_CAP: "Multi-core steps strictly respect the subject CPU core limit",
    }
)
GLOBAL_PREFERENCES[category]['cuda'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Enable CUDA for GPUable commands",
    tooltip='NVIDIA GPU-based computation',
    default='false',
    dependency='is_cuda',
    dependency_fail_tooltip="GPU does not support CUDA",
)
GLOBAL_PREFERENCES[category]['max_subj_gpu'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="GPU process limit per subject",
    tooltip="The limit should be equal or lesser than the number of physical GPU",
    default=1,
    range=[1, 5],
    pref_requirement={GlobalPrefCategoryList.PERFORMANCE: [('cuda', True)]},
    pref_requirement_fail_tooltip="Requires CUDA",
)
category = GlobalPrefCategoryList.OPTIONAL_SERIES
GLOBAL_PREFERENCES[category] = {}
for data_input in DataInputList:
    if data_input.value.optional:
        GLOBAL_PREFERENCES[category][data_input.value.name] = PreferenceEntry(
            input_type=InputTypes.BOOLEAN,
            label=data_input.value.label,
            default='false',
            restart=True,
        )

category = GlobalPrefCategoryList.MAIL_SETTINGS
GLOBAL_PREFERENCES[category] = {}
GLOBAL_PREFERENCES[category]['enabled'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Enabled",
    tooltip="Toggle on/off the mail report sending service. If enabled, a mail report will be sent to your email at each workflow completion",
    default='false'
)
GLOBAL_PREFERENCES[category]['address'] = PreferenceEntry(
    input_type=InputTypes.TEXT,
    label="Address",
    tooltip="The POP3/IMAP address of your mail host",
    default=""
)
GLOBAL_PREFERENCES[category]['port'] = PreferenceEntry(
    input_type=InputTypes.INT,
    label="Port",
    tooltip="The port indicated in your mail host documentation",
    default=0,
    range=[1, 1000]
)
GLOBAL_PREFERENCES[category]['username'] = PreferenceEntry(
    input_type=InputTypes.TEXT,
    label="Username",
    tooltip="Your email",
    default=""
)
GLOBAL_PREFERENCES[category]['password'] = PreferenceEntry(
    input_type=InputTypes.PASSWORD,
    label="Password",
    tooltip="Your password email",
    default=""
)
GLOBAL_PREFERENCES[category]['use_ssl'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Use SSL",
    tooltip="True if your mail host requires the SSL security protocol",
    default='true'
)
GLOBAL_PREFERENCES[category]['use_tls'] = PreferenceEntry(
    input_type=InputTypes.BOOLEAN,
    label="Use TLS",
    tooltip="True if your mail host requires the TLS security protocol. TLS is not used if SSL is active",
    default='false'
)

DEFAULT_WF = {}
DEFAULT_WF[WORKFLOW_TYPES.STRUCTURAL] = {
    DataInputList.T13D: {
        'hippo_amyg_labels': 'false',
        'flat1': 'false',
    },
    DataInputList.DTI: {
        'tractography': 'true',
    },
    DataInputList.ASL: {
        'ai': 'false'
    },
    DataInputList.PET: {
        'ai': 'false'
    },
}
DEFAULT_WF[WORKFLOW_TYPES.FUNCTIONAL] = {
    DataInputList.T13D: {
        'hippo_amyg_labels': 'true',
        'flat1': 'true',
    },
    DataInputList.DTI: {
        'tractography': 'false',
    },
    DataInputList.ASL: {
        'ai': 'true'
    },
    DataInputList.PET: {
        'ai': 'true'
    },
}
