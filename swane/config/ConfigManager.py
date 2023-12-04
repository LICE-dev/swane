import configparser
from swane import strings, __version__
from swane.config.preference_list import *
from swane.utils.DataInputList import DataInputList


class ConfigManager(configparser.ConfigParser):

    # Overrides to accept non-str stringable object as section keys
    def __getitem__(self, key):
        return super().__getitem__(str(key))

    def __setitem__(self, key, value):
        super().__setitem__(str(key), value)

    def getboolean(self, section, option, **kwargs):
        return super().getboolean(str(section), option, **kwargs)

    def getint(self, section, option, **kwargs):
        return super().getint(str(section), option, **kwargs)

    def __init__(self, pt_folder: str = None):
        """

        Parameters
        ----------
        pt_folder: str
            The patient folder path. Non in global all configuration
        """
        super(ConfigManager, self).__init__()

        # First set some internal values differentiating global from patient pref objects
        if pt_folder is not None:
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI SPECIFICHE DI UN UTENTE COPIO ALCUNI VALORI DALLE IMPOSTAZIONI GLOBALI
            self.global_config = False
            self.config_file = os.path.join(os.path.join(pt_folder, ".config"))
        else:
            # NEL CASO STIA GESTENDO LE IMPOSTAZIONI GLOBALI DELL'APP
            self.global_config = True
            self.config_file = os.path.abspath(os.path.join(
                os.path.expanduser("~"), "." + strings.APPNAME))

        # Load default pref from pref list
        self.load_default_wf_settings(save=False)

        # check if this version need pref reset
        try:
            force_pref_reset = self.getboolean(GlobalPrefCategoryList.MAIN, 'force_pref_reset')
        except:
            force_pref_reset = False

        reset_pref = False

        # if version need pref reset, load olg config file in a temp variable to get just last_swane_version
        try:
            if force_pref_reset:
                temp_config = configparser.ConfigParser()
                temp_config.read(self.config_file)
                if __version__ != temp_config[GlobalPrefCategoryList.MAIN]['last_swane_version']:
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

    def load_default_wf_settings(self, save):
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

            self.set_wf_option(tmp_config[GlobalPrefCategoryList.MAIN]['default_wf_type'])
        if save:
            self.save()

    def set_wf_option(self, wf):
        if self.global_config:
            return
        wf = str(wf)
        self[DataInputList.T13D]['wf_type'] = wf
        for category in DEFAULT_WF[wf]:
            for key in DEFAULT_WF[wf][category]:
                self[category][key] = DEFAULT_WF[wf][category][key]

    def save(self):
        with open(self.config_file, "w") as openedFile:
            self.write(openedFile)

    def get_patients_folder(self):
        try:
            if self.global_config and os.path.exists(self[GlobalPrefCategoryList.MAIN]["patients_folder"]):
                return self[GlobalPrefCategoryList.MAIN]["patients_folder"]
        except:
            pass
        return ''

    def set_patients_folder(self, path):
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]["patients_folder"] = path
            self.save()

    def get_max_pt(self):
        if not self.global_config:
            return 1
        try:
            return self.getint(GlobalPrefCategoryList.PERFORMANCE, 'max_pt')
        except:
            return 1

    def get_patients_prefix(self):
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['patients_prefix']
        return ''

    def get_default_dicom_folder(self):
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['default_dicom_folder']
        return ''

    def get_slicer_path(self):
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_path']
        return ''

    def set_slicer_path(self, path):
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]['slicer_path'] = path

    def get_slicer_version(self):
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_version']

    def set_slicer_version(self, slicer_version):
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]['slicer_version'] = slicer_version

    def is_optional_series_enabled(self, series_name):
        if self.global_config:
            try:
                return self.getboolean(GlobalPrefCategoryList.OPTIONAL_SERIES, str(series_name))
            except:
                return False
        return False

    def get_slicer_scene_ext(self):
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]['slicer_scene_ext']
        return ''

    def get_pt_wf_type(self):
        if not self.global_config:
            try:
                return self[DataInputList.T13D].getint('wf_type')
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

    def get_wf_hippo_pref(self):
        try:
            return self.getboolean(DataInputList.T13D, 'hippo_amyg_labels')
        except:
            return False

    def get_wf_freesurfer_pref(self):
        try:
            return self.getboolean(DataInputList.T13D, 'freesurfer')
        except:
            return False

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

    def get_last_pid(self):
        try:
            return self.getint(GlobalPrefCategoryList.MAIN, 'last_pid')
        except:
            pass
        return -1

