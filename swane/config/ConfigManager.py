import configparser
import math
from configparser import SectionProxy
from typing import Literal, cast

from swane.resources import strings
from swane import __version__
from swane.config.preference_list import *
from swane.utils.CryptographyManager import CryptographyManager
from swane.utils.DataInputList import DataInputList
from enum import Enum
from swane.config.config_enums import (
    WorkflowTypes,
    GlobalPrefCategoryList,
    PerformanceProfile,
)
from swane.utils.MailManager import MailManager


class ConfigManager(configparser.ConfigParser):

    VALIDATION_SUFFIX = "_validation"

    # Overrides to accept non-str stringable object as section keys
    def __getitem__(
        self, key: str | DataInputList | GlobalPrefCategoryList
    ) -> SectionProxy:
        return super().__getitem__(str(key))

    def __setitem__(self, key, value):
        super().__setitem__(str(key), value)

    def __init__(
        self,
        subject_folder: str = None,
        global_base_folder: str = None,
        global_config: "ConfigManager | None" = None,
    ):
        """
        Parameters
        ----------
        subject_folder: path
            The subject folder path. None in global all configuration
        global_base_folder: path, optional
            An alternative folder for global configuration file. Default is None
        global_config: ConfigManager, optional
            The already loaded global configuration used to initialize a subject
            configuration. It is not persisted in the subject configuration.
        """
        super(ConfigManager, self).__init__()
        self._section_defaults = {}
        self._source_global_config = global_config

        # First set some internal values differentiating global from subject pref objects
        if subject_folder is not None:
            self.global_config = False
            self.config_file = os.path.abspath(os.path.join(subject_folder, ".config"))
        else:
            if global_base_folder is None or not os.path.exists(global_base_folder):
                global_base_folder = os.path.expanduser("~")
            self.global_config = True
            self.config_file = os.path.abspath(
                os.path.join(global_base_folder, "." + strings.APPNAME)
            )

        # Load default pref from pref list
        self._load_defaults(save=False)
        # The global configuration is only a source for subject defaults during
        # initialization; subject changes must remain independent afterwards.
        self._source_global_config = None

        # check if this version need pref reset
        force_pref_reset = self.getboolean_safe(
            GlobalPrefCategoryList.MAIN, "force_pref_reset"
        )

        # if version need pref reset, load old config file in a temp variable to get just last_swane_version
        reset_pref = False
        if force_pref_reset:
            try:
                # main.last_swane_version should exist in both global and  subject config file
                temp_config = configparser.ConfigParser()
                temp_config.read(self.config_file, encoding="utf-8")
                last_swane_version = temp_config[str(GlobalPrefCategoryList.MAIN)][
                    "last_swane_version"
                ]
                if __version__ != last_swane_version:
                    reset_pref = True
            except:
                # otherwise assume outdated version
                reset_pref = True

        if not reset_pref and os.path.exists(self.config_file):
            self.read(self.config_file, encoding="utf-8")

            # Migrate options renamed in a later SWANe version, in place, before
            # the re-validation loop below relies on the current option names.
            # The new option name is already present at this point with its
            # default value (populated by _load_defaults above), so the old
            # persisted value must overwrite it unconditionally, not only when
            # the new key is still missing.
            for section, renames in RENAMED_PREFERENCES.items():
                if section not in self:
                    continue
                for old, new in renames.items():
                    if old in self[section]:
                        self[section][new] = self[section][old]
                        self.remove_option(section, old)

            # Cycle all read values and reassign them to invoke validate_type without rewriting read method
            for section in self._section_defaults.keys():
                for option in self._section_defaults[section].keys():
                    if self._section_defaults[section][option].default_at_startup:
                        self.set(
                            section,
                            option,
                            self._section_defaults[section][option].default,
                        )
                    else:
                        self.set(section, option, self[section][option])

            # set last_swane_version in subject config to ensure force_pref_reset compatibility
            if str(GlobalPrefCategoryList.MAIN) not in self:
                self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]["last_swane_version"] = __version__

        self.save()

    def reload(self):
        """
        Reload the configuration file
        """
        self.read(self.config_file, encoding="utf-8")

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
                            self[category][pref] = GLOBAL_PREFERENCES[category][
                                pref
                            ].default.name
                        else:
                            self[category][pref] = str(
                                GLOBAL_PREFERENCES[category][pref].default
                            )
                        if GLOBAL_PREFERENCES[category][pref].validate_on_change:
                            self[category][
                                pref + ConfigManager.VALIDATION_SUFFIX
                            ] = "true"

            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self[data_input] = {}
                    self._section_defaults[str(data_input)] = WF_PREFERENCES[data_input]
                    for pref in WF_PREFERENCES[data_input]:
                        if isinstance(WF_PREFERENCES[data_input][pref].default, Enum):
                            self[data_input][pref] = WF_PREFERENCES[data_input][
                                pref
                            ].default.name
                        else:
                            self[data_input][pref] = str(
                                WF_PREFERENCES[data_input][pref].default
                            )
        else:
            tmp_config = self._source_global_config
            if tmp_config is None:
                tmp_config = ConfigManager()
            elif not tmp_config.global_config:
                raise ValueError("Subject configuration requires a global config")
            for data_input in DataInputList:
                if data_input in WF_PREFERENCES:
                    self._section_defaults[str(data_input)] = WF_PREFERENCES[data_input]
                    self[data_input] = tmp_config[data_input]
            self[GlobalPrefCategoryList.MAIN] = {}
            self[GlobalPrefCategoryList.MAIN]["last_swane_version"] = tmp_config[
                GlobalPrefCategoryList.MAIN
            ]["last_swane_version"]
            self[GlobalPrefCategoryList.MAIN]["force_pref_reset"] = tmp_config[
                GlobalPrefCategoryList.MAIN
            ]["force_pref_reset"]

            self.set_workflow_option(
                tmp_config.getenum_safe(GlobalPrefCategoryList.MAIN, "default_wf_type")
            )
        if save:
            self.save()

    def set_workflow_option(self, workflow_type: WorkflowTypes):
        """
        Apply a workflow_type preset

        Parameters
        ----------
        workflow_type: WorkflowTypes
            The preset to apply
        """
        if self.global_config:
            return
        if type(workflow_type) is not WorkflowTypes:
            return
        self[DataInputList.T13D]["wf_type"] = workflow_type.name
        for category in DEFAULT_WF[workflow_type]:
            for key in DEFAULT_WF[workflow_type][category]:
                self[category][key] = DEFAULT_WF[workflow_type][category][key]

    def save(self):
        """
        Save the current preferences to the config file
        """
        with open(self.config_file, "w", encoding="utf-8") as openedFile:
            self.write(openedFile)

    def get_main_working_directory(self) -> str:
        """
        Returns
        -------
        A string containing the main working directory
        """
        try:
            if self.global_config and os.path.exists(
                self[GlobalPrefCategoryList.MAIN]["main_working_directory"]
            ):
                return self[GlobalPrefCategoryList.MAIN]["main_working_directory"]
        except:
            pass
        return ""

    def set_main_working_directory(self, main_working_dir_path: str):
        """
        Set the main working directory

        Parameters
        ----------
        main_working_dir_path: path
            the new path

        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN][
                "main_working_directory"
            ] = main_working_dir_path
            self.save()

    def get_max_subject_tabs(self) -> int:
        """
        Returns
        -------
        An int containing the maximum subject tab number
        """
        return self.getint_safe(GlobalPrefCategoryList.PERFORMANCE, "max_subj")

    def get_subjects_prefix(self) -> str:
        """
        Returns
        -------
        A string containing the subject folder prefix
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]["subjects_prefix"]
        return ""

    def get_default_dicom_folder(self) -> str:
        """
        Returns
        -------
        A string containing the default dicom folder name
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]["default_dicom_folder"]
        return ""

    def get_slicer_path(self) -> str:
        """
        Returns
        -------
        A string containing the slicer executable path
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]["slicer_path"]
        return ""

    def get_slicer_validator(self) -> bool:
        """
        Returns
        -------
        A bool, true if slicer executable validation needs to be checked
        """
        if self.global_config:
            return self.getboolean_safe(
                GlobalPrefCategoryList.MAIN, "slicer_path" + self.VALIDATION_SUFFIX
            )
        return False

    def set_slicer_validator(self, value: bool):
        """
        Set whether the slicer executable validation needs to be checked

        Parameters
        ----------
        value: bool
            True if slicer executable validation needs to be checked
        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN][
                "slicer_path" + self.VALIDATION_SUFFIX
            ] = str(value)

    def set_slicer_path(self, slicer_path: str):
        """
        Set the slicer executable path

        Parameters
        ----------
        slicer_path: path
            the new path

        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]["slicer_path"] = slicer_path

    def get_slicer_version(self) -> str:
        """
        Returns
        -------
        A string containing the current slicer version
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]["slicer_version"]

    def set_slicer_version(self, slicer_version: str):
        """
        Set the Slicer version

        Parameters
        ----------
        slicer_version: str
            the Slicer version

        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]["slicer_version"] = slicer_version

    def get_slicer_extensions_state(self) -> str:
        """
        Returns
        -------
        The JSON string recorded by the last full Slicer check (Slicer revision
        and extension install folders), or "" if none was recorded
        """
        if self.global_config:
            return self[GlobalPrefCategoryList.MAIN]["slicer_extensions_state"]
        return ""

    def set_slicer_extensions_state(self, state: str):
        """
        Set the JSON string describing where the Slicer extensions are installed

        Parameters
        ----------
        state: str
            JSON produced by SlicerCheckWorker.encode_extensions_state
        """
        if self.global_config:
            # configparser interpolation: a literal "%" must be doubled
            self[GlobalPrefCategoryList.MAIN]["slicer_extensions_state"] = (
                state.replace("%", "%%")
            )

    def get_accepted_license_version(self, tool_id: str) -> str:
        """
        Return the tool version whose license the user last accepted, or "".

        Parameters
        ----------
        tool_id: str
            Canonical tool id ("fsl", "freesurfer", "slicer", "dcm2niix").
        """
        if not self.global_config:
            return ""
        key = "accepted_license_" + tool_id
        if key not in self[GlobalPrefCategoryList.MAIN]:
            return ""
        return self[GlobalPrefCategoryList.MAIN][key]

    def set_accepted_license_version(self, tool_id: str, tool_version: str):
        """
        Store the tool version whose license the user accepted.

        Parameters
        ----------
        tool_id: str
            Canonical tool id ("fsl", "freesurfer", "slicer", "dcm2niix").
        tool_version: str
            The detected tool version accepted by the user.
        """
        if self.global_config:
            self[GlobalPrefCategoryList.MAIN]["accepted_license_" + tool_id] = str(
                tool_version
            )

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
        return self.getboolean_safe(
            GlobalPrefCategoryList.OPTIONAL_SERIES, str(series_name)
        )

    def get_slicer_scene_ext(self) -> str:
        """
        Returns
        -------
        A string containing the default slicer scene extension
        """
        if self.global_config:
            return self.getenum_safe(
                GlobalPrefCategoryList.MAIN, "slicer_scene_ext"
            ).value
        return None

    def get_subject_workflow_type(self) -> Enum:
        """
        Returns
        -------
        The Enum of default workflow type
        """
        return self.getenum_safe(DataInputList.T13D, "wf_type")

    def get_workflow_hippo_pref(self) -> bool:
        """
        Returns
        -------
        True if hippocampal segmentation is enabled
        """
        return self.getboolean_safe(DataInputList.T13D, "hippo_amyg_labels")

    def get_workflow_freesurfer_pref(self) -> FreesurferStep:
        """
        Returns
        -------
        True if freesurfer analysis is enabled
        """
        return self.getenum_safe(DataInputList.T13D, "freesurfer_step")

    def get_workflow_synthseg_fast_pref(self) -> bool:
        """
        Returns
        -------
        True if SynthSeg fast mode is enabled
        """
        return self.getboolean_safe(DataInputList.T13D, "synthseg_fast")

    def get_mail_manager(self) -> MailManager:
        """
        Returns
        -------
        An initialized MailManager
        """

        mail_manager_enabled = self.getboolean_safe(
            GlobalPrefCategoryList.MAIL_SETTINGS, "enabled"
        )
        if not mail_manager_enabled:
            return None

        server_address = self[GlobalPrefCategoryList.MAIL_SETTINGS]["address"]
        server_port = self.getint_safe(GlobalPrefCategoryList.MAIL_SETTINGS, "port")
        username = self[GlobalPrefCategoryList.MAIL_SETTINGS]["username"]
        password = CryptographyManager.decrypt(
            self[GlobalPrefCategoryList.MAIL_SETTINGS]["password"]
        )
        use_ssl = self.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, "use_ssl")
        use_tls = self.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, "use_tls")

        if server_address == "" or server_port <= 0 or username == "" or password == "":
            return None

        mail_manager = MailManager(
            server_address=server_address,
            server_port=server_port,
            username=username,
            password=password,
            use_ssl=use_ssl,
            use_tls=use_tls,
        )

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
        for section in WF_PREFERENCES:
            for option in WF_PREFERENCES[section]:
                if WF_PREFERENCES[section][option].dependency is not None:
                    dep_check = getattr(
                        dependency_manager,
                        WF_PREFERENCES[section][option].dependency,
                        None,
                    )
                    if dep_check is None or not callable(dep_check) or not dep_check():
                        self[section][option] = "false"
                        changed = True
                        continue

                if self._reset_unavailable_enum_option(
                    section, option, WF_PREFERENCES[section][option], dependency_manager
                ):
                    changed = True

                if WF_PREFERENCES[section][option].resource is not None:
                    resource_check = getattr(
                        ResourceManager,
                        WF_PREFERENCES[section][option].resource,
                        None,
                    )
                    if (
                        resource_check is None
                        or not callable(resource_check)
                        or not resource_check(config=self)
                    ):
                        self[section][option] = "false"
                        changed = True

        # Global-only engine choices (e.g. the Synth-tools engines) are not part
        # of WF_PREFERENCES: reset any whose selected option lost its dependency
        # (e.g. an FSL engine when FSL is not installed) to the default.
        if self.global_config:
            for category in GLOBAL_PREFERENCES:
                for option in GLOBAL_PREFERENCES[category]:
                    # Boolean global preferences whose external dependency is
                    # missing (e.g. an optional series that needs a tool) are
                    # turned off.
                    entry = GLOBAL_PREFERENCES[category][option]
                    if (
                        entry.input_type == InputTypes.BOOLEAN
                        and entry.dependency is not None
                        and self.has_option(str(category), option)
                        and self.getboolean_safe(category, option)
                    ):
                        dep_check = getattr(dependency_manager, entry.dependency, None)
                        if (
                            dep_check is None
                            or not callable(dep_check)
                            or not dep_check()
                        ):
                            self[category][option] = "false"
                            changed = True
                            continue

                    if self._reset_unavailable_enum_option(
                        category,
                        option,
                        GLOBAL_PREFERENCES[category][option],
                        dependency_manager,
                    ):
                        changed = True

        if changed:
            self.save()

    def _reset_unavailable_enum_option(
        self, section, option: str, entry, dependency_manager
    ) -> bool:
        """
        Reset an enum preference to its default if the dependency of its current
        option is not met.

        Parameters
        ----------
        section: GlobalPrefCategoryList | DataInputList
            The preference section
        option: str
            The preference key
        entry: PreferenceEntry
            The preference metadata
        dependency_manager: DependencyManager
            The application dependencies

        Returns
        -------
        True if the preference was reset.
        """
        if (
            entry.input_type != InputTypes.ENUM
            or not self.has_option(str(section), option)
            or self[section][option] not in entry.value_enum.__members__
        ):
            return False
        value_enum = entry.value_enum[self[section][option]]
        if value_enum not in entry.option_dependency:
            return False
        dep_check = getattr(
            dependency_manager, entry.option_dependency[value_enum][0], None
        )
        if dep_check is None or not callable(dep_check) or dep_check():
            return False
        default = self._section_defaults[str(section)][option].default
        self[section][option] = (
            default.name if isinstance(default, Enum) else str(default)
        )
        return True

    def get_last_pid(self) -> tuple[int, str | None]:
        """
        Returns
        -------
        The last application process ID as an int and its creation time as a string
        """
        last_pid = self.getint_safe(GlobalPrefCategoryList.MAIN, "last_pid")
        last_pid_create_time = self[GlobalPrefCategoryList.MAIN].get(
            "last_pid_create_time"
        )
        return last_pid, last_pid_create_time

    def getboolean_safe(
        self,
        section: str | GlobalPrefCategoryList | DataInputList,
        option: str,
        *,
        raw=False,
        vars=None,
        **kwargs
    ) -> bool:
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
            if (
                section in self._section_defaults
                and option in self._section_defaults[section]
            ):
                if type(self._section_defaults[section][option].default) is list:
                    ret = str(self._section_defaults[section][option].default[0])
                else:
                    ret = str(self._section_defaults[section][option].default)
                if ret.lower() in configparser.ConfigParser.BOOLEAN_STATES:
                    return configparser.ConfigParser.BOOLEAN_STATES[ret.lower()]
        raise Exception()

    def getint_safe(
        self,
        section: str | GlobalPrefCategoryList | DataInputList,
        option: str,
        *,
        raw=False,
        vars=None,
        **kwargs
    ) -> int:
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
            if (
                section in self._section_defaults
                and option in self._section_defaults[section]
            ):
                if type(self._section_defaults[section][option].default) is list:
                    return int(self._section_defaults[section][option].default[0])
                else:
                    return int(self._section_defaults[section][option].default)
        raise Exception("Error for %s - %s" % (str(section), str(option)))

    def getfloat_safe(
        self,
        section: str | GlobalPrefCategoryList | DataInputList,
        option: str,
        *,
        raw=False,
        vars=None,
        **kwargs
    ) -> float:
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
            if (
                section in self._section_defaults
                and option in self._section_defaults[section]
            ):
                if type(self._section_defaults[section][option].default) is list:
                    return float(self._section_defaults[section][option].default[0])
                else:
                    return float(self._section_defaults[section][option].default)
        raise Exception("Error for %s - %s" % (str(section), str(option)))

    def getenum_safe(
        self,
        section: str | GlobalPrefCategoryList | DataInputList,
        option: str,
        *,
        raw: bool = False,
        vars=None,
        **kwargs
    ) -> Enum:
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
        if (
            section not in self._section_defaults
            or option not in self._section_defaults[section]
        ):
            raise Exception("Error for %s - %s" % (str(section), str(option)))
        if self._section_defaults[section][option].value_enum is None:
            raise Exception("No value_enum for %s - %s" % (str(section), str(option)))

        if (
            self[section][option]
            in self._section_defaults[section][option].value_enum.__members__
        ):
            return self._section_defaults[section][option].value_enum[
                self[section][option]
            ]
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
            if (
                section in self._section_defaults
                and option in self._section_defaults[section]
            ):
                if self._section_defaults[section][option].input_type == InputTypes.INT:
                    try:
                        return int(value)
                    except:
                        return int(self._section_defaults[section][option].default)
                elif (
                    self._section_defaults[section][option].input_type
                    == InputTypes.ENUM
                ):
                    if (
                        value
                        in self._section_defaults[section][
                            option
                        ].value_enum.__members__
                    ):
                        return value
                    else:
                        return self._section_defaults[section][option].default.name
                elif (
                    self._section_defaults[section][option].input_type
                    == InputTypes.FLOAT
                ):
                    try:
                        return float(value)
                    except:
                        return float(self._section_defaults[section][option].default)
                elif (
                    self._section_defaults[section][option].input_type
                    == InputTypes.BOOLEAN
                ):
                    if value.lower() in configparser.ConfigParser.BOOLEAN_STATES:
                        return value
                    elif (
                        self._section_defaults[section][option].default.lower()
                        in configparser.ConfigParser.BOOLEAN_STATES
                    ):
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

    #: Share of this computer each resource profile lets SWANe use, as
    #: (percentage of the total RAM, fraction of the CPU cores). The share is
    #: the total for all the subjects analysed at the same time.
    RESOURCE_PROFILE_SHARES = {
        PerformanceProfile.LOW_RESOURCE: (50, 1 / 3),
        PerformanceProfile.BALANCED: (70, 1 / 2),
        PerformanceProfile.MAX_PERF: (85, 1),
    }

    @staticmethod
    def get_resource_budget(profile: PerformanceProfile) -> tuple[float, int]:
        """
        Total RAM and CPU cores a resource profile lets SWANe use.

        Parameters
        ----------
        profile: PerformanceProfile
            The resource profile.

        Returns
        -------
        The RAM in GB and the number of CPU cores, both shared by all the
        subjects analysed at the same time.
        """
        ram_perc, cpu_fraction = ConfigManager.RESOURCE_PROFILE_SHARES[profile]
        ram_gb = max(
            ResourceManager.get_ram_by_perc(ram_perc),
            ResourceManager.get_minimum_subject_ram(),
        )
        cpu = max(1, int(ResourceManager.get_max_cpu() * cpu_fraction))
        return ram_gb, cpu

    @staticmethod
    def get_max_parallel_subjects(profile: PerformanceProfile) -> int:
        """
        Most subjects a resource profile can analyse at the same time, giving
        each one at least the minimum RAM allocation and staying within the
        subject tab limit range.

        Parameters
        ----------
        profile: PerformanceProfile
            The resource profile.

        Returns
        -------
        The maximum number of subjects analysed at the same time.
        """
        ram_gb, cpu = ConfigManager.get_resource_budget(profile)
        tab_limit = GLOBAL_PREFERENCES[GlobalPrefCategoryList.PERFORMANCE][
            "max_subj"
        ].range[1]
        by_ram = int(ram_gb // ResourceManager.get_minimum_subject_ram())
        return max(1, min(tab_limit, by_ram, cpu))

    @staticmethod
    def get_resource_profile_values(
        profile: PerformanceProfile, parallel_subjects: int = 1
    ) -> dict:
        """
        Performance preferences that a resource profile sets.

        The profile budget (see get_resource_budget) is split among the
        subjects analysed at the same time, so that all the subject tabs
        together never exceed it.

        Parameters
        ----------
        profile: PerformanceProfile
            The resource profile.
        parallel_subjects: int, optional
            Subjects analysed at the same time (the subject tab limit), clamped
            to 1..get_max_parallel_subjects(profile). Default is 1.

        Returns
        -------
        A dict mapping each PERFORMANCE preference key the profile sets to its
        (non-serialized) value.
        """
        ram_gb, cpu = ConfigManager.get_resource_budget(profile)
        parallel_subjects = max(
            1,
            min(
                int(parallel_subjects), ConfigManager.get_max_parallel_subjects(profile)
            ),
        )
        return {
            "ram_gb": math.floor(ram_gb / parallel_subjects * 100) / 100,
            "max_subj_cpu": max(1, cpu // parallel_subjects),
            "max_subj": parallel_subjects,
        }

    def apply_resource_profile(
        self, profile: PerformanceProfile, parallel_subjects: int = 1
    ):

        if not self.global_config:
            return

        for key, value in ConfigManager.get_resource_profile_values(
            profile, parallel_subjects
        ).items():
            self[GlobalPrefCategoryList.PERFORMANCE][key] = str(value)
