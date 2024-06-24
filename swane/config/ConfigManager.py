import configparser
from swane import strings, __version__
from swane.config.preference_list import *
from swane.utils.CryptographyManager import CryptographyManager
from swane.utils.DataInputList import DataInputList
from enum import Enum
from swane.config.config_enums import WORKFLOW_TYPES, GlobalPrefCategoryList
from swane.utils.MailManager import MailManager


class ConfigManager(configparser.ConfigParser):

    # Overrides to accept non-str stringable object as section keys
    def __getitem__(self, key):
        return super().__getitem__(str(key))

    def __setitem__(self, key, value):
        super().__setitem__(str(key), value)

    def __init__(self, subject_folder: str = None, global_base_folder: str = None):
        """
        Parameters
        ----------
        subject_folder: path
            The subject folder path. None in global all configuration
        global_base_folder: path, optional
            An alternative folder for global configuration file. Default is None
        """
        super(ConfigManager, self).__init__()
        self._section_defaults = {}

        # First set some internal values differentiating global from subject pref objects
        if subject_folder is not None:
            self.global_config = False
            self.config_file = os.path.abspath(os.path.join(subject_folder, ".config"))
        else:
            if global_base_folder is None or not os.path.exists(global_base_folder):
                global_base_folder = os.path.expanduser("~")
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
            # set last_swane_version in subject config to ensure force_pref_reset compatibility
            if str(GlobalPrefCategoryList.MAIN) not in self:
                self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]['last_swane_version'] = __version__

        self.save()

    def reload(self):
        """
        Reload the configuration file
        """
        self.read(self.config_file)

    def reset_to_defaults(self):
        """
        Discard current values and reload defaults
        """
        self._load_defaults(save=True)

    def _load_defaults(self, save: bool):
        """
        Loop the default dicts and insert default values in this object

        Parameters
        ----------
        save: bool
            If True, save the preferences
        """
        if self.global_config:
            for category in GlobalPrefCategoryList:
                if not save:
                    self[category] = {}
                    self._section_defaults[str(category)] = GLOBAL_PREFERENCES[category]
                    for pref in GLOBAL_PREFERENCES[category]:
                        if isinstance(GLOBAL_PREFERENCES[category][pref].default, Enum):
                            self[category][pref] = GLOBAL_PREFERENCES[category][pref].default.name
                        else:
                            self[category][pref] = str(GLOBAL_PREFERENCES[category][pref].default)

            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self[data_input] = {}
                    self._section_defaults[str(data_input)] = WF_PREFERENCES[data_input]
                    for pref in WF_PREFERENCES[data_input]:
                        if isinstance(WF_PREFERENCES[data_input][pref].default, Enum):
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
        """
        Apply a workflow_type preset

        Parameters
        ----------
        workflow_type: WORKFLOW_TYPES
            The preset to apply
        """
        if self.global_config:
            return
        if type(workflow_type) is not WORKFLOW_TYPES:
            return
        self[DataInputList.T13D]['wf_type'] = workflow_type.name
        for category in DEFAULT_WF[workflow_type]:
            for key in DEFAULT_WF[workflow_type][category]:
                self[category][key] = DEFAULT_WF[workflow_type][category][key]

    def save(self):
        """
        Save the current preferences to the config file
        """
        with open(self.config_file, "w") as openedFile:
            self.write(openedFile)

    def get_main_working_directory(self) -> str:
        """
        Returns
        -------
        A string containing the main working directory
        """
        try:
            if self.global_config and os.path.exists(self[GlobalPrefCategoryList.MAIN]["main_working_directory"]):
                return self[GlobalPrefCategoryList.MAIN]["main_working_directory"]
        except:
            pass
        return ''

    def set_main_working_directory(self, main_working_dir_path: str):
        """
        Set the main working directory

        Parameters
        ----------
        main_working_dir_path: path
            the new path

        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]["main_working_directory"] = main_working_dir_path
            self.save()

    def get_max_subject_tabs(self) -> int:
        """
        Returns
        -------
        An int containing the maximum subject tab number
        """
        return self.getint_safe(GlobalPrefCategoryList.PERFORMANCE, 'max_subj')

    def get_subjects_prefix(self) -> str:
        """
        Returns
        -------
        A string containing the subject folder prefix
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['subjects_prefix']
        return ''

    def get_default_dicom_folder(self) -> str:
        """
        Returns
        -------
        A string containing the default dicom folder name
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['default_dicom_folder']
        return ''

    def get_slicer_path(self) -> str:
        """
        Returns
        -------
        A string containing the slicer executable path
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_path']
        return ''

    def set_slicer_path(self, slicer_path: str):
        """
        Set the slicer executable path

        Parameters
        ----------
        slicer_path: path
            the new path

        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]['slicer_path'] = slicer_path

    def get_slicer_version(self) -> str:
        """
        Returns
        -------
        A string containing the current slicer version
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_version']

    def set_slicer_version(self, slicer_version: str):
        """
        Set the Slicer version

        Parameters
        ----------
        slicer_version: str
            the Slicer version

        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]['slicer_version'] = slicer_version

    def is_optional_series_enabled(self, series_name: DataInputList) -> bool:
        """
        Check if an optional series is enabled

        Parameters
        ----------
        series_name: DataInputList
            The series to check

        Returns
        -------
        True if the specified series is enabled
        """
        return self.getboolean_safe(GlobalPrefCategoryList.OPTIONAL_SERIES, str(series_name))

    def get_slicer_scene_ext(self) -> str:
        """
        Returns
        -------
        A string containing the default slicer scene extension
        """
        if self.global_config:
            return self.getenum_safe(GlobalPrefCategoryList.MAIN, 'slicer_scene_ext').value
        return None

    def get_subject_workflow_type(self) -> Enum:
        """
        Returns
        -------
        The Enum of default workflow type
        """
        return self.getenum_safe(DataInputList.T13D, 'wf_type')

    def get_workflow_hippo_pref(self) -> bool:
        """
        Returns
        -------
        True if hippocampal segmentation is enabled
        """
        return self.getboolean_safe(DataInputList.T13D, 'hippo_amyg_labels')

    def get_workflow_freesurfer_pref(self) -> bool:
        """
        Returns
        -------
        True if freesurfer analysis is enabled
        """
        return self.getboolean_safe(DataInputList.T13D, 'freesurfer')
    
    def get_mail_manager(self) -> MailManager:
        """
        Returns
        -------
        An initialized MailManager
        """
        
        mail_manager_enabled = self.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, 'enabled')
        if not mail_manager_enabled:
            return None
        
        server_address = self[GlobalPrefCategoryList.MAIL_SETTINGS]["address"]
        server_port = self.getint_safe(GlobalPrefCategoryList.MAIL_SETTINGS, 'port')
        username = self[GlobalPrefCategoryList.MAIL_SETTINGS]["username"]
        password = CryptographyManager.decrypt(self[GlobalPrefCategoryList.MAIL_SETTINGS]['password'])
        use_ssl = self.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, 'use_ssl')
        use_tls = self.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, 'use_tls')
        
        if server_address == "" or server_port == "" or username == "" or password == "":
            return None
        
        mail_manager = MailManager(server_address=server_address, server_port=server_port, username=username, password=password, use_ssl=use_ssl, use_tls=use_tls)
        
        return mail_manager

    def check_dependencies(self, dependency_manager):
        """
        Check if dependencies of each preference entry are met, otherwise set them to false

        Parameters
        ----------
        dependency_manager: DependencyManager
            The application dependencies

        """
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
        """
        Returns
        -------
        The last application process ID as an int
        """
        return self.getint_safe(GlobalPrefCategoryList.MAIN, 'last_pid')

    def getboolean_safe(self, section: str, option: str, *, raw=False, vars=None, **kwargs) -> bool:
        """
        Get an option value as bool or, if invalid, its default value

        Parameters
        ----------
        section: str
            The configuration section
        option: str
            The configuration option
        raw: bool, optional
            Unused, passed to super(). Default is False
        vars
            Unused, passed to Super(). Default is None

        Returns
        -------
        The option values bool
        """
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

    def getint_safe(self, section: str, option: str, *, raw=False, vars=None, **kwargs) -> int:
        """
        Get an option value as int or, if invalid, its default value

        Parameters
        ----------
        section: str
            The configuration section
        option: str
            The configuration option
        raw: bool, optional
            Unused, passed to super(). Default is False
        vars
            Unused, passed to Super(). Default is None

        Returns
        -------
        The option values int
        """
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

    def getfloat_safe(self, section: str, option: str, *, raw=False, vars=None, **kwargs) -> float:
        """
        Get an option value as float or, if invalid, its default value

        Parameters
        ----------
        section: str
            The configuration section
        option: str
            The configuration option
        raw: bool, optional
            Unused, passed to super(). Default is False
        vars
            Unused, passed to Super(). Default is None

        Returns
        -------
        The option values as float
        """
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

    def getenum_safe(self, section: str, option: str, *, raw: bool = False, vars=None, **kwargs) -> Enum:
        """
        Get an option value as Enum or, if invalid, its default value

        Parameters
        ----------
        section: str
            The configuration section
        option: str
            The configuration option
        raw: bool, optional
            Unused, passed to super(). Default is False
        vars
            Unused, passed to Super(). Default is None

        Returns
        -------
        The option values as Enum
        """
        section = str(section)
        if self._section_defaults[section][option].value_enum is None:
            raise Exception("No value_enum for %s - %s" % (str(section), str(option)))

        if self[section][option] in self._section_defaults[section][option].value_enum.__members__:
            return self._section_defaults[section][option].value_enum[self[section][option]]
        else:
            return self._section_defaults[section][option].default

    def validate_type(self, section: str = "", option: str = "", value: str = ""):
        """
        Set an option after checking for type

        Parameters
        ----------
        section: str
            The configuration section
        option: str
            The configuration option
        value: str, optional
            The value to be checked. DEfault is None

        Returns
        -------
        The value cast to its type or the default option value
        """
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

    def set(self, section: str, option: str, value: str = None):
        """
        Set an option after checking for type

        Parameters
        ----------
        section: str
            The configuration section
        option: str
            The configuration option
        value: str, optional
            The value to be checked. DEfault is None

        Returns
        -------
        True if the application preference has a valide Slicer path
        """
        if value is not None:
            value = str(self.validate_type(section, option, value))
        super().set(section, option, value)
