import configparser
import os
from swane import strings
from swane.utils.DataInput import DataInputList
from swane.utils.wf_preferences import wf_preferences


# todo valutare di spostare le key delle configurazioni in file costanti esterno
class ConfigManager(configparser.ConfigParser):

    WORKFLOW_TYPES = ["Structural Workflow", "Morpho-Functional Workflow"]
    BEDPOSTX_CORES = ["No limit", "Soft cap", "Hard Cap"]
    SLICER_EXTENSIONS = ["mrb", "mrml"]

    DEFAULT_WF = {}
    DEFAULT_WF['0'] = {
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
    DEFAULT_WF['1'] = {
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

    def __init__(self, pt_folder=None, freesurfer=None):
        super(ConfigManager, self).__init__()

        if pt_folder is not None:
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI SPECIFICHE DI UN UTENTE COPIO ALCUNI VALORI DALLE IMPOSTAZIONI GLOBALI
            self.global_config = False
            self.config_file = os.path.join(os.path.join(pt_folder, ".config"))
            self.freesurfer = freesurfer
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
                'lastPID': '-1',
                'maxPt': '1',
                'maxPtCPU': '-1',
                'slicerSceneExt': '0',
                'defaultWfType': '0',
                'defaultdicomfolder': 'dicom',
                'resourceMonitor': 'false',
                'bedpostx_core': '0',
            }

            self['OPTIONAL_SERIES'] = {}

            for data_input in DataInputList().values():
                if data_input.optional:
                    self['OPTIONAL_SERIES'][data_input.name] = 'false'

        self.load_default_wf_settings(save=False)

    def set_wf_option(self, wf):
        if self.global_config:
            return
        wf = str(wf)
        for category in self.DEFAULT_WF[wf]:
            for key in self.DEFAULT_WF[wf][category]:
                self[category][key] = self.DEFAULT_WF[wf][category][key]

        self.update_freesurfer_pref()

    def update_freesurfer_pref(self):
        if not self.is_freesurfer():
            self['WF_OPTION']['freesurfer'] = 'false'
        if not self.is_freesurfer_matlab():
            self['WF_OPTION']['hippoAmygLabels'] = 'false'
            self['WF_OPTION']['hippoAmygLabels'] = 'false'

    def is_freesurfer(self):
        if self.freesurfer is None:
            return False
        return self.freesurfer[0]
    
    def is_freesurfer_matlab(self):
        if self.freesurfer is None:
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
                return self.getboolean(DataInputList.T13D, 'freesurfer')
            except:
                return False
        return False

    def get_pt_wf_hippo(self):
        if not self.global_config:
            try:
                return self.getboolean(DataInputList.T13D, 'hippo_amyg_labels')
            except:
                return False
        return False

    def load_default_wf_settings(self, save=True):
        if self.global_config:
            for data_input in DataInputList().values():
                if data_input.name in wf_preferences:
                    self[data_input.name] = {}
                    for pref in wf_preferences[data_input.name]:
                        if isinstance(wf_preferences[data_input.name][pref]['default'], list):
                            self[data_input.name][pref] = "0"
                        else:
                            self[data_input.name][pref] = str(wf_preferences[data_input.name][pref]['default'])
        else:
            tmp_config = ConfigManager()
            for data_input in DataInputList().values():
                if data_input.name in wf_preferences:
                    self[data_input.name] = tmp_config[data_input.name]

            self.set_wf_option(tmp_config['MAIN']['defaultWfType'])
        if save:
            self.save()
