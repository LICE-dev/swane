import configparser
from swane import strings, __version__
from swane.config.preference_list import *
from swane.utils.DataInputList import DataInputList
from enum import Enum
from inspect import isclass
from swane.config.config_enums import WORKFLOW_TYPES, SLICER_EXTENSIONS


class ConfigManager(configparser.ConfigParser):

    # Overrides to accept non-str stringable object as section keys
    def __getitem__(self, key):
        return super().__getitem__(str(key))

    def __setitem__(self, key, value):
        super().__setitem__(str(key), value)

    def __init__(self, patient_folder: str = None, global_base_folder: str = None):
        """

        Parameters
        ----------
        patient_folder: str
            The patient folder path. None in global all configuration
        """
        super(ConfigManager, self).__init__()
        self._section_defaults = {}

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
        self._load_defaults(save=False)

        # check if this version need pref reset
        force_pref_reset = self.getboolean_safe(GlobalPrefCategoryList.MAIN, 'force_pref_reset')

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
            # Cycle all read values and reassign them to invoke validate_type without rewriting read method
            for section in self._section_defaults.keys():
                for option in self._section_defaults[section].keys():
                    self.set(section, option, self[section][option])
            # set last_swane_version in patient config to ensure force_pref_reset compatibility
            if str(GlobalPrefCategoryList.MAIN) not in self:
                self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]['last_swane_version'] = __version__

        self.save()

    def reload(self):
        self.read(self.config_file)

    def reset_to_defaults(self):
        self._load_defaults(save=True)

    def _load_defaults(self, save: bool):
        if self.global_config:
            for category in GlobalPrefCategoryList:
                if not save:
                    self[category] = {}
                    self._section_defaults[str(category)] = GLOBAL_PREFERENCES[category]
                    for pref in GLOBAL_PREFERENCES[category]:
                        if issubclass(type(GLOBAL_PREFERENCES[category][pref].default), Enum):
                            self[category][pref] = GLOBAL_PREFERENCES[category][pref].default.name
                        else:
                            self[category][pref] = str(GLOBAL_PREFERENCES[category][pref].default)

            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self[data_input] = {}
                    self._section_defaults[str(data_input)] = WF_PREFERENCES[data_input]
                    for pref in WF_PREFERENCES[data_input]:
                        if issubclass(type(WF_PREFERENCES[data_input][pref].default), Enum):
                            self[data_input][pref] = WF_PREFERENCES[data_input][pref].default.name
                        else:
                            self[data_input][pref] = str(WF_PREFERENCES[data_input][pref].default)
        else:
            tmp_config = ConfigManager()
            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self._section_defaults[str(data_input)] = WF_PREFERENCES[data_input]
                    self[data_input] = tmp_config[data_input]
            self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]['last_swane_version'] = tmp_config[GlobalPrefCategoryList.MAIN]['last_swane_version']
            self[GlobalPrefCategoryList.MAIN]['force_pref_reset'] = tmp_config[GlobalPrefCategoryList.MAIN]['force_pref_reset']

            self.set_workflow_option(tmp_config.getenum_safe(GlobalPrefCategoryList.MAIN, 'default_wf_type'))
        if save:
            self.save()

    def set_workflow_option(self, workflow_type: WORKFLOW_TYPES):
        if self.global_config:
            return
        if type(workflow_type) is not WORKFLOW_TYPES:
            return
        self[DataInputList.T13D]['wf_type'] = workflow_type.name
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
        return self.getint_safe(GlobalPrefCategoryList.PERFORMANCE, 'max_pt')

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

    def is_optional_series_enabled(self, series_name: DataInputList) -> bool:
        return self.getboolean_safe(GlobalPrefCategoryList.OPTIONAL_SERIES, str(series_name))

    def get_slicer_scene_ext(self) -> str:
        if self.global_config:
            return self.getenum_safe(GlobalPrefCategoryList.MAIN, 'slicer_scene_ext').value
        return None

    def get_patient_workflow_type(self) -> Enum:
        return self.getenum_safe(DataInputList.T13D, 'wf_type')

    def get_workflow_hippo_pref(self) -> bool:
        return self.getboolean_safe(DataInputList.T13D, 'hippo_amyg_labels')

    def get_workflow_freesurfer_pref(self) -> bool:
        return self.getboolean_safe(DataInputList.T13D, 'freesurfer')

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
        return self.getint_safe(GlobalPrefCategoryList.MAIN, 'last_pid')

    def getboolean_safe(self, section: Enum | str, option: str, *, raw=False, vars=None, **kwargs) -> bool:
        section = str(section)
        try:
            return self.getboolean(section, option, raw=raw, vars=vars)
        except:
            if section in self._section_defaults and option in self._section_defaults[section]:
                if type(self._section_defaults[section]) is list:
                    ret = self._section_defaults[section].default[0]
                else:
                    ret = self._section_defaults[section].default
                if ret.lower() in configparser.ConfigParser.BOOLEAN_STATES:
                    return configparser.ConfigParser.BOOLEAN_STATES[ret.lower()]
        raise Exception()

    def getint_safe(self, section: Enum | str, option: str, *, raw=False, vars=None, **kwargs) -> int:
        section = str(section)
        try:
            return self.getint(section, option, raw=raw, vars=vars)
        except:
            if section in self._section_defaults and option in self._section_defaults[section]:
                if type(self._section_defaults[section][option].default) is list:
                    return 0
                else:
                    return int(self._section_defaults[section][option].default)
        raise Exception("Error for %s - %s" % (str(section), str(option)))

    def getfloat_safe(self, section: Enum | str, option: str, *, raw=False, vars=None, **kwargs) -> float:
        section = str(section)
        try:
            return self.getfloat(section, option, raw=raw, vars=vars)
        except:
            if section in self._section_defaults and option in self._section_defaults[section]:
                if type(self._section_defaults[section][option].default) is list:
                    return float(self._section_defaults[section][option].default[0])
                else:
                    return float(self._section_defaults[section][option].default)
        raise Exception("Error for %s - %s" % (str(section), str(option)))

    def getenum_safe(self, section: Enum | str, option: str, *, raw=False, vars=None, **kwargs) -> Enum:
        section = str(section)
        if self._section_defaults[section][option].value_enum is None:
            raise("No value_enum for %s - %s" % (str(section), str(option)))

        if self[section][option] in self._section_defaults[section][option].value_enum.__members__:
            return self._section_defaults[section][option].value_enum[self[section][option]]
        else:
            return self._section_defaults[section][option].default

    def validate_type(self, section="", option="", value=""):
        if section != "" and option != "" and value != "":
            if section in self._section_defaults and option in self._section_defaults[section]:
                if self._section_defaults[section][option].input_type == InputTypes.INT:
                    try:
                        return int(value)
                    except:
                        return int(self._section_defaults[section][option].default)
                elif self._section_defaults[section][option].input_type == InputTypes.ENUM:
                    if value in self._section_defaults[section][option].value_enum.__members__:
                        return value
                    else:
                        return self._section_defaults[section][option].default.name
                elif self._section_defaults[section][option].input_type == InputTypes.FLOAT:
                    try:
                        return float(value)
                    except:
                        return float(self._section_defaults[section][option].default)
                elif self._section_defaults[section][option].input_type == InputTypes.BOOLEAN:
                    if value.lower() in configparser.ConfigParser.BOOLEAN_STATES:
                        return value
                    elif self._section_defaults[section][option].default.lower() in configparser.ConfigParser.BOOLEAN_STATES:
                        return self._section_defaults[section][option].default.lower()
        return value

    def set(self, section, option, value=None):
        """Set an option after checking for type"""
        if value is not None:
            value = str(self.validate_type(section, option, value))
        super().set(section, option, value)
