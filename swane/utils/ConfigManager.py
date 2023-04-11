import configparser
import os
from swane import strings
from swane.utils.DataInput import DataInputList


# todo valutare di spostare le key delle configurazioni in file costanti esterno
class ConfigManager(configparser.ConfigParser):

    WORKFLOW_TYPES = ["Structural Workflow", "Morpho-Functional Workflow"]
    SLICER_EXTENSIONS = ["mrb", "mrml"]
    SLICE_TIMING = ['Unknown', 'Regular up', 'Regular down', 'Interleaved']
    BLOCK_DESIGNS = ['rArA...', 'rArBrArB...']

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
              "mdlf": ['Middle Longitudinal Fasciculuc', 'false', 0],
              "or": ['Optic Radiation', 'true', 0],
              "str": ['Superior Thalamic Radiation', 'false', 0],
              "ac": ['Anterior Commissure', 'false', 0],
              "uf": ['Uncinate Fasciculus', 'false', 0],
              "vof": ['Vertical Occipital Fasciculus', 'false', 0],
              "null": ['Vertical Occipital Fasciculus', 'false', 0],
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



    DEFAULT_WF = {}
    DEFAULT_WF['0'] = {
        'wftype': '0',
        'freesurfer': 'true',
        'hippoAmygLabels': 'false',
        'domap': 'false',
        'ai': 'false',
        'tractography': 'true',
    }
    DEFAULT_WF['1'] = {
        'wftype': '1',
        'freesurfer': 'true',
        'hippoAmygLabels': 'true',
        'domap': 'true',
        'ai': 'true',
        'tractography': 'false',
    }

    def __init__(self, pt_folder=None, freesurfer=None):
        super(ConfigManager, self).__init__()

        if pt_folder is not None:
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI SPECIFICHE DI UN UTENTE COPIO ALCUNI VALORI DALLE IMPOSTAZIONI GLOBALI
            self.global_config = False
            self.config_file = os.path.join(os.path.join(pt_folder, ".config"))
            self.freesurfer=freesurfer
        else:
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI GLOBALI DELL'APP
            self.global_config = True
            self.config_file = os.path.abspath(os.path.join(
                os.path.expanduser("~"), "." + strings.APPNAME))

        self.create_default_config()

        if os.path.exists(self.config_file):
            self.read(self.config_file)

        self.save()

    def reload(self):
        self.read(self.config_file)

    def create_default_config(self):
        if self.global_config:
            self['MAIN'] = {
                'patientsfolder': '',
                'patientsprefix': 'pt_',
                'slicerPath': '',
                'shortcutPath': '',
                'lastPID': '-1',
                'maxPt': '1',
                'maxPtCPU': '-1',
                'slicerSceneExt': '0',
                'defaultWfType': '0',
                'fmritaskduration': '30',
                'defaultdicomfolder': 'dicom'
            }

            self['OPTIONAL_SERIES'] = {}

            for data_input in DataInputList().values():
                if data_input.optional:
                    self['OPTIONAL_SERIES'][data_input.name] = 'false'

            self['DEFAULTTRACTS'] = {}

            for index, key in enumerate(ConfigManager.TRACTS):
                self['DEFAULTTRACTS'][key] = ConfigManager.TRACTS[key][1]
        else:
            tmp_config = ConfigManager()
            self.set_wf_option(tmp_config['MAIN']['defaultWfType'])
            self['FMRI'] = {}

            for x in range(DataInputList.FMRI_NUM):
                self['FMRI']['task_%d_name_a' % x] = 'TaskA'
                self['FMRI']['task_%d_name_b' % x] = 'TaskB'
                self['FMRI']['task_%d_duration' % x] = tmp_config['MAIN']['fmritaskduration']
                self['FMRI']['rest_%d_duration' % x] = tmp_config['MAIN']['fmritaskduration']
                self['FMRI']['task_%d_tr' % x] = 'auto'
                self['FMRI']['task_%d_vols' % x] = 'auto'
                self['FMRI']['task_%d_st' % x] = '0'
                self['FMRI']['task_%d_blockdesign' % x] = '0'
                self['FMRI']['task_%d_del_start_vols' % x] = '0'
                self['FMRI']['task_%d_del_end_vols' % x] = '0'

            self['DEFAULTTRACTS'] = tmp_config['DEFAULTTRACTS']

    def set_wf_option(self, wf):
        if self.global_config:
            return
        wf = str(wf)
        self['WF_OPTION'] = ConfigManager.DEFAULT_WF[wf]
        self.update_freesurfer_pref()

    def update_freesurfer_pref(self):
        if not self.is_freesurfer():
            self['WF_OPTION']['freesurfer'] = 'false'
        if not self.is_freesurfer_matlab():
            self['WF_OPTION']['hippoAmygLabels'] = 'false'
            self['WF_OPTION']['hippoAmygLabels'] = 'false'

    def is_freesurfer(self):
        if self.global_config or self.freesurfer is None:
            return False
        return self.freesurfer[0]
    
    def is_freesurfer_matlab(self):
        if self.global_config or self.freesurfer is None:
            return False
        return self.freesurfer[0]

    def save(self):
        with open(self.config_file, "w") as openedFile:
            self.write(openedFile)

    def get_patients_folder(self):
        if self.global_config:
            return self["MAIN"]["PatientsFolder"]
        return ''

    def set_patients_folder(self, path):
        if self.global_config:
            self["MAIN"]["PatientsFolder"] = path

    def get_shortcut_path(self):
        if self.global_config:
            return self['MAIN']['shortcutPath']
        return ''

    def set_shortcut_path(self, path):
        if self.global_config:
            self['MAIN']['shortcutPath'] = path

    def get_max_pt(self):
        if not self.global_config:
            return 1
        try:
            return self.getint('MAIN', 'maxPt')
        except:
            return 1

    def get_patientsprefix(self):
        if self.global_config:
            return self['MAIN']['patientsprefix']
        return ''

    def get_default_dicom_folder(self):
        if self.global_config:
            return self['MAIN']['defaultdicomfolder']
        return ''

    def get_slicer_path(self):
        if self.global_config:
            return self['MAIN']['slicerPath']
        return ''

    def set_slicer_path(self, path):
        if self.global_config:
            self['MAIN']['slicerPath'] = path

    def is_optional_series_enabled(self, series_name):
        if self.global_config:
            try:
                return self.getboolean('OPTIONAL_SERIES', series_name)
            except:
                return False
        return False

    def get_slicer_scene_ext(self):
        if self.global_config:
            return self['MAIN']['slicerSceneExt']
        return ''

    def get_pt_wf_type(self):
        if not self.global_config:
            try:
                return self['WF_OPTION'].getint('wfType')
            except:
                return 0
        return 0

    def get_pt_wf_freesurfer(self):
        if not self.global_config:
            try:
                return self.getboolean('WF_OPTION', 'freesurfer')
            except:
                return False
        return False

    def get_pt_wf_hippo(self):
        if not self.global_config:
            try:
                return self.getboolean('WF_OPTION', 'hippoAmygLabels')
            except:
                return False
        return False
