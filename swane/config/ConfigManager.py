import configparser
from swane import strings, __version__
from swane.config.preference_list import *
from swane.utils.DataInputList import DataInputList
from enum import Enum


class ConfigManager(configparser.ConfigParser):

    # Overrides to accept non-str stringable object as section keys
    def __getitem__(self, key):
        return super().__getitem__(str(key))

    def __setitem__(self, key, value):
        super().__setitem__(str(key), value)

    def getboolean(self, section, option, **kwargs) -> bool:
        return super().getboolean(str(section), option, **kwargs)

    def getfloat(self, section, option, **kwargs) -> bool:
        return super().getfloat(str(section), option, **kwargs)

    def getint(self, section, option, **kwargs) -> int:
        return super().getint(str(section), option, **kwargs)

    def __init__(self, patient_folder: str = None, global_base_folder: str = None):
        """

        Parameters
        ----------
        patient_folder: str
            The patient folder path. None in global all configuration
        """
        super(ConfigManager, self).__init__()

        # First set some internal values differentiating global from patient pref objects
        if patient_folder is not None:
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI SPECIFICHE DI UN UTENTE COPIO ALCUNI VALORI DALLE IMPOSTAZIONI GLOBALI
            self.global_config = False
            self.config_file = os.path.join(os.path.join(patient_folder, ".config"))
        else:
            if global_base_folder is None or not os.path.exists(global_base_folder):
                global_base_folder = os.path.expanduser("~")
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI GLOBALI DELL'APP
            self.global_config = True
            self.config_file = os.path.abspath(os.path.join(global_base_folder, "." + strings.APPNAME))

        # Load default pref from pref list
        self.load_default_workflow_settings(save=False)

        # check if this version need pref reset
        force_pref_reset = save_get_boolean(self, GLOBAL_PREFERENCES, GlobalPrefCategoryList.MAIN, 'force_pref_reset')

        reset_pref = False

        # if version need pref reset, load olg config file in a temp variable to get just last_swane_version
        try:
            if force_pref_reset:
                if self.global_config:
                    last_swane_version = self[GlobalPrefCategoryList.MAIN]['last_swane_version']
                else:
                    temp_config = configparser.ConfigParser()
                    temp_config.read(self.config_file)
                    last_swane_version = temp_config[GlobalPrefCategoryList.MAIN]['last_swane_version']
                if __version__ != last_swane_version:
                    reset_pref = True
        except:
            pass

        if not reset_pref and os.path.exists(self.config_file):
            self.read(self.config_file)
            if str(GlobalPrefCategoryList.MAIN) not in self:
                self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]['last_swane_version'] = __version__

        self.save()

    def reload(self):
        self.read(self.config_file)

    def load_default_workflow_settings(self, save: bool):
        if self.global_config:
            for category in GlobalPrefCategoryList:
                if not save:
                    self[category] = {}
                    for pref in GLOBAL_PREFERENCES[category]:
                        if isinstance(GLOBAL_PREFERENCES[category][pref].default, list):
                            self[category][pref] = "0"
                        else:
                            self[category][pref] = str(GLOBAL_PREFERENCES[category][pref].default)

            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self[data_input] = {}
                    for pref in WF_PREFERENCES[data_input]:
                        if isinstance(WF_PREFERENCES[data_input][pref].default, list):
                            self[data_input][pref] = "0"
                        else:
                            self[data_input][pref] = str(WF_PREFERENCES[data_input][pref].default)
        else:
            tmp_config = ConfigManager()
            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self[data_input] = tmp_config[data_input]
            self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]['last_swane_version'] = tmp_config[GlobalPrefCategoryList.MAIN]['last_swane_version']
            self[GlobalPrefCategoryList.MAIN]['force_pref_reset'] = tmp_config[GlobalPrefCategoryList.MAIN]['force_pref_reset']

            self.set_workflow_option(tmp_config[GlobalPrefCategoryList.MAIN]['default_wf_type'])
        if save:
            self.save()

    def set_workflow_option(self, workflow_type: int | str):
        if self.global_config:
            return
        workflow_type = str(workflow_type)
        self[DataInputList.T13D]['wf_type'] = workflow_type
        for category in DEFAULT_WF[workflow_type]:
            for key in DEFAULT_WF[workflow_type][category]:
                self[category][key] = DEFAULT_WF[workflow_type][category][key]

    def save(self):
        with open(self.config_file, "w") as openedFile:
            self.write(openedFile)

    def get_main_working_directory(self) -> str:
        try:
            if self.global_config and os.path.exists(self[GlobalPrefCategoryList.MAIN]["main_working_directory"]):
                return self[GlobalPrefCategoryList.MAIN]["main_working_directory"]
        except:
            pass
        return ''

    def set_main_working_directory(self, path: str):
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]["main_working_directory"] = path
            self.save()

    def get_max_patient_tabs(self) -> int:
        return save_get_int(self, GLOBAL_PREFERENCES, GlobalPrefCategoryList.PERFORMANCE, 'max_pt')

    def get_patients_prefix(self) -> str:
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['patients_prefix']
        return ''

    def get_default_dicom_folder(self) -> str:
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['default_dicom_folder']
        return ''

    def get_slicer_path(self) -> str:
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_path']
        return ''

    def set_slicer_path(self, path: str):
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]['slicer_path'] = path

    def get_slicer_version(self) -> str:
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_version']

    def set_slicer_version(self, slicer_version: str):
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]['slicer_version'] = slicer_version

    def is_optional_series_enabled(self, series_name: str) -> bool:
        return save_get_boolean(self, GLOBAL_PREFERENCES, GlobalPrefCategoryList.OPTIONAL_SERIES, str(series_name))

    def get_slicer_scene_ext(self) -> str:
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_scene_ext']
        return ''

    def get_patient_workflow_type(self) -> int:
        return save_get_int(self, WF_PREFERENCES, DataInputList.T13D, 'wf_type')

    def get_workflow_hippo_pref(self) -> bool:
        return save_get_boolean(self, WF_PREFERENCES, DataInputList.T13D, 'hippo_amyg_labels')

    def get_workflow_freesurfer_pref(self) -> bool:
        return save_get_boolean(self, WF_PREFERENCES, DataInputList.T13D, 'freesurfer')

    def check_dependencies(self, dependency_manager):
        changed = False
        for category in WF_PREFERENCES:
            for key in WF_PREFERENCES[category]:
                if WF_PREFERENCES[category][key].dependency is not None:
                    dep_check = getattr(dependency_manager, WF_PREFERENCES[category][key].dependency, None)
                    if dep_check is None or not callable(dep_check) or not dep_check():
                        self[category][key] = "false"
                        changed = True
        if changed:
            self.save()

    def get_last_pid(self) -> int:
        return save_get_int(self, GLOBAL_PREFERENCES, GlobalPrefCategoryList.MAIN, 'last_pid')


def save_get_boolean(config: ConfigManager | configparser.SectionProxy, defaults: dict[Enum, PreferenceEntry], section: Enum, option: str) -> bool:
    try:
        if type(config) is ConfigManager:
            return config.getboolean(section, option)
        elif type(config) is configparser.SectionProxy:
            return config.getboolean(option)
    except:
        if section in defaults and option in defaults[section]:
            if type(defaults[section][option].default) is list:
                ret = defaults[section][option].default[0]
            else:
                ret = defaults[section][option].default
            if ret.lower() in configparser.ConfigParser.BOOLEAN_STATES:
                return configparser.ConfigParser.BOOLEAN_STATES[ret.lower()]
    raise Exception()


def save_get_int(config: ConfigManager | configparser.SectionProxy, defaults: dict[Enum, PreferenceEntry], section: Enum, option: str) -> int:
    try:
        if type(config) is ConfigManager:
            return config.getint(section, option)
        elif type(config) is configparser.SectionProxy:
            return config.getint(option)
    except:
        if section in defaults and option in defaults[section]:
            if type(defaults[section][option].default) is list:
                return 0
            else:
                return int(defaults[section][option].default)
    raise Exception("Error for %s - %s" % (str(section), str(option)))


def save_get_float(config: ConfigManager | configparser.SectionProxy, defaults: dict[Enum, PreferenceEntry], section: Enum, option: str) -> float:
    try:
        if type(config) is ConfigManager:
            return config.getfloat(section, option)
        elif type(config) is configparser.SectionProxy:
            return config.getfloat(option)
    except:
        if section in defaults and option in defaults[section]:
            if type(defaults[section][option].default) is list:
                return float(defaults[section][option].default[0])
            else:
                return float(defaults[section][option].default)
    raise Exception("Error for %s - %s" % (str(section), str(option)))
