"""Unit tests for :class:`swane.config.ConfigManager.ConfigManager`."""

import configparser
import json
import os
import shutil

import pytest
from packaging.version import Version

import swane
from swane.utils.ResourceManager import ResourceManager

import swane.config.ConfigManager as config_manager_module
from swane.config.ConfigManager import ConfigManager
from swane.config.preference_list import (
    GLOBAL_PREFERENCES,
    PREF_RESET_BEFORE_VERSION,
    WF_PREFERENCES,
)
from swane.config.config_enums import (
    GlobalPrefCategoryList,
    PerformanceProfile,
    VeinDetectionMode,
    WorkflowTypes,
)
from swane.utils.DataInputList import DataInputList
from swane.utils.CryptographyManager import CryptographyManager
from swane.utils.MailManager import MailManager


class TestGlobalConfig:

    def test_init_creates_all_sections(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        assert config.global_config is True
        assert config.config_file == os.path.join(str(tmp_path), ".SWANe")
        for category in GlobalPrefCategoryList:
            assert config.has_section(str(category))

    def test_persistence_across_reload(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config[GlobalPrefCategoryList.MAIN]["default_dicom_folder"] = "custom_dcm"
        config.save()

        reloaded = ConfigManager(global_base_folder=str(tmp_path))
        assert (
            reloaded[GlobalPrefCategoryList.MAIN]["default_dicom_folder"]
            == "custom_dcm"
        )

    def test_main_working_directory(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        missing = os.path.join(str(tmp_path), "subjects")
        config.set_main_working_directory(missing)
        assert config.get_main_working_directory() == ""  # not created yet
        os.makedirs(missing)
        config.set_main_working_directory(missing)
        assert config.get_main_working_directory() == missing

    def test_slicer_path_and_version(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        assert config.get_slicer_path() == ""
        config.set_slicer_path("/opt/Slicer/Slicer")
        assert config.get_slicer_path() == "/opt/Slicer/Slicer"
        config.set_slicer_version("5.4.0")
        assert config.get_slicer_version() == "5.4.0"
        assert config.get_slicer_revision() == ""
        config.set_slicer_extensions_state('{"revision": "34045", "paths": {}}')
        assert config.get_slicer_revision() == "34045"
        config.set_slicer_extensions_state('{"revision": null, "paths": {}}')
        assert config.get_slicer_revision() == ""

    def test_scene_ext_and_default_dicom_folder(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        assert config.get_slicer_scene_ext() in ("mrb", "mrml")
        assert config.get_default_dicom_folder() != ""

    def test_apply_resource_profile(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        perf = GlobalPrefCategoryList.PERFORMANCE
        config[perf]["max_subj"] = "3"
        for profile in PerformanceProfile:
            config.apply_resource_profile(profile)
            ram_gb, cpu = ConfigManager.get_resource_budget(profile)
            assert config.getfloat_safe(perf, "ram_gb") == pytest.approx(
                ram_gb, abs=0.01
            )
            assert config.getint_safe(perf, "max_subj_cpu") == cpu
            # The profile does not touch the subject tab limit
            assert config[perf]["max_subj"] == "3"

    def test_resources_are_per_subject_tab_at_load(self, tmp_path):
        # The values apply to each subject tab: more tabs never lower them
        config = ConfigManager(global_base_folder=str(tmp_path))
        perf = GlobalPrefCategoryList.PERFORMANCE
        ram_gb = str(ResourceManager.get_maximum_ram())
        config[perf]["max_subj"] = str(ResourceManager.MAX_PARALLEL_SUBJECTS)
        config[perf]["ram_gb"] = ram_gb
        config[perf]["max_subj_cpu"] = "-1"
        config.save()

        config = ConfigManager(global_base_folder=str(tmp_path))
        assert config.get_max_subject_tabs() == ResourceManager.MAX_PARALLEL_SUBJECTS
        assert config[perf]["ram_gb"] == ram_gb
        assert config.getint_safe(perf, "max_subj_cpu") == -1


class TestSafeGetters:

    def test_getint_safe_falls_back_to_default(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        # writing a non-int through set() coerces to the default value
        config.set(str(GlobalPrefCategoryList.PERFORMANCE), "max_subj", "not-an-int")
        assert isinstance(
            config.getint_safe(GlobalPrefCategoryList.PERFORMANCE, "max_subj"), int
        )

    def test_getboolean_safe(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        value = config.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, "enabled")
        assert isinstance(value, bool)

    def test_getboolean_safe_falls_back_to_string_default(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        # Simulate a hand-edited/corrupted config file storing a non-boolean
        # value, bypassing the validating set() override.
        configparser.ConfigParser.set(
            config, str(GlobalPrefCategoryList.MAIL_SETTINGS), "enabled", "garbage"
        )
        # "enabled" default is the string "false": fallback must return the bool.
        assert (
            config.getboolean_safe(GlobalPrefCategoryList.MAIL_SETTINGS, "enabled")
            is False
        )

    def test_getboolean_safe_falls_back_to_bool_default(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        # "reconall" default is a Python bool (False), not the string "false":
        # the fallback must handle it without raising.
        configparser.ConfigParser.set(
            config, str(GlobalPrefCategoryList.SYNTH), "reconall", "garbage"
        )
        assert config.getboolean_safe(GlobalPrefCategoryList.SYNTH, "reconall") is False

    def test_getfloat_safe_falls_back_to_default(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        # Simulate a hand-edited/corrupted config file, bypassing the
        # validating set() override. WF_PREFERENCES sections (DataInputList)
        # go through the same fallback code path as GLOBAL_PREFERENCES ones,
        # so this is also what every workflow node relies on for e.g. bet_thr.
        configparser.ConfigParser.set(
            config, str(DataInputList.T13D), "bet_thr", "garbage"
        )
        assert config.getfloat_safe(DataInputList.T13D, "bet_thr") == 0.3

    def test_getenum_safe_falls_back_to_default(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        configparser.ConfigParser.set(
            config, str(DataInputList.VENOUS_MR), "vein_detection_mode", "garbage"
        )
        assert (
            config.getenum_safe(DataInputList.VENOUS_MR, "vein_detection_mode")
            is VeinDetectionMode.KURTOSIS
        )


class TestFmriRestingPreferenceMigration:

    @staticmethod
    def _new_subject_config(tmp_path, subject_name="subj"):
        # global_base_folder must already exist: ConfigManager silently falls
        # back to the real home directory otherwise (os.path.expanduser("~")).
        global_dir = tmp_path / "global"
        global_dir.mkdir(exist_ok=True)
        global_config = ConfigManager(global_base_folder=str(global_dir))
        subject_folder = tmp_path / subject_name
        subject_folder.mkdir()
        config = ConfigManager(str(subject_folder), global_config=global_config)
        return config, subject_folder

    def test_melodic_dim_migrates_to_ic_dim(self, tmp_path):
        config, subject_folder = self._new_subject_config(tmp_path)
        section = str(DataInputList.FMRI_RS)
        config[section]["ic_dim"] = "0"
        config.save()

        # Simulate a pre-rename config file written by an older SWANe version.
        config_path = subject_folder / ".config"
        text = config_path.read_text().replace("ic_dim = 0", "melodic_dim = 12")
        config_path.write_text(text)

        reloaded_global = ConfigManager(global_base_folder=str(tmp_path / "global"))
        reloaded = ConfigManager(str(subject_folder), global_config=reloaded_global)

        assert reloaded.getint_safe(section, "ic_dim") == 12
        assert "melodic_dim" not in reloaded[section]
        assert "melodic_dim" not in config_path.read_text()

    def test_melodic_dim_migrates_in_global_config(self, tmp_path):
        # WF_PREFERENCES sections (e.g. the resting-state fMRI category) are
        # also persisted in the global config, as the default applied to new
        # subjects, so the migration must run there too.
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        config = ConfigManager(global_base_folder=str(global_dir))
        section = str(DataInputList.FMRI_RS)

        config_path = global_dir / ".SWANe"
        text = config_path.read_text().replace("ic_dim = 0", "melodic_dim = 12")
        config_path.write_text(text)

        reloaded = ConfigManager(global_base_folder=str(global_dir))

        assert reloaded.getint_safe(section, "ic_dim") == 12
        assert "melodic_dim" not in reloaded[section]
        assert "melodic_dim" not in config_path.read_text()


class TestPreferenceResetOnUpgrade:
    """Files written before PREF_RESET_BEFORE_VERSION are reset to defaults,
    later ones are kept, whatever the persisted force_pref_reset says."""

    MAIN = str(GlobalPrefCategoryList.MAIN)
    FMRI = str(DataInputList.FMRI_0)

    @staticmethod
    def _write(path, sections):
        parser = configparser.ConfigParser()
        for section, options in sections.items():
            parser[section] = options
        with open(path, "w", encoding="utf-8") as f:
            parser.write(f)

    @staticmethod
    def _read(path):
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        return parser

    @staticmethod
    def _run_as_version(monkeypatch, version):
        monkeypatch.setattr(config_manager_module, "__version__", version)
        monkeypatch.setattr(
            GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]["last_swane_version"],
            "default",
            version,
        )

    def _global_file(self, global_dir, version, force_pref_reset="false"):
        main = {"default_dicom_folder": "custom_dcm"}
        if version is not None:
            main["last_swane_version"] = version
        if force_pref_reset is not None:
            main["force_pref_reset"] = force_pref_reset
        self._write(global_dir / ".SWANe", {self.MAIN: main})

    def _subject_file(self, subject_dir, version, force_pref_reset="false"):
        main = {}
        if version is not None:
            main["last_swane_version"] = version
        if force_pref_reset is not None:
            main["force_pref_reset"] = force_pref_reset
        self._write(
            subject_dir / ".config",
            {self.MAIN: main, self.FMRI: {"task_duration": "42"}},
        )

    @pytest.fixture
    def dirs(self, tmp_path):
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        subject_dir = tmp_path / "subj"
        subject_dir.mkdir()
        return global_dir, subject_dir

    def _load(self, global_dir, subject_dir):
        global_config = ConfigManager(global_base_folder=str(global_dir))
        subject_config = ConfigManager(str(subject_dir), global_config=global_config)
        return global_config, subject_config

    def _assert_kept(self, global_dir, subject_dir, global_config, subject_config):
        assert global_config[self.MAIN]["default_dicom_folder"] == "custom_dcm"
        assert subject_config[self.FMRI]["task_duration"] == "42"
        on_disk = self._read(global_dir / ".SWANe")
        assert on_disk[self.MAIN]["default_dicom_folder"] == "custom_dcm"
        assert self._read(subject_dir / ".config")[self.FMRI]["task_duration"] == "42"

    def _assert_reset(self, global_dir, subject_dir, global_config, subject_config):
        default_dicom = GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN][
            "default_dicom_folder"
        ].default
        default_duration = str(
            WF_PREFERENCES[DataInputList.FMRI_0]["task_duration"].default
        )
        assert global_config[self.MAIN]["default_dicom_folder"] == default_dicom
        assert subject_config[self.FMRI]["task_duration"] == default_duration
        on_disk = self._read(global_dir / ".SWANe")
        assert on_disk[self.MAIN]["default_dicom_folder"] == default_dicom
        assert (
            self._read(subject_dir / ".config")[self.FMRI]["task_duration"]
            == default_duration
        )

    def test_threshold_is_this_release_and_not_above_current_version(self):
        # Release decision: reset everything written before the intermediate
        # 0.2.5 builds. A threshold above __version__ would reset every
        # configuration at every start, the file being always "too old".
        assert PREF_RESET_BEFORE_VERSION == "0.2.5"
        assert Version(PREF_RESET_BEFORE_VERSION) <= Version(swane.__version__)

    def test_02x_global_and_subject_configs_are_reset(self, dirs):
        global_dir, subject_dir = dirs
        self._global_file(global_dir, "0.2.1.1")
        self._subject_file(subject_dir, "0.2.1.1")

        global_config, subject_config = self._load(global_dir, subject_dir)

        self._assert_reset(global_dir, subject_dir, global_config, subject_config)
        for config in (global_config, subject_config):
            assert config[self.MAIN]["last_swane_version"] == swane.__version__

    def test_configs_from_threshold_version_are_kept(self, dirs):
        global_dir, subject_dir = dirs
        self._global_file(global_dir, PREF_RESET_BEFORE_VERSION)
        self._subject_file(subject_dir, PREF_RESET_BEFORE_VERSION)

        global_config, subject_config = self._load(global_dir, subject_dir)

        self._assert_kept(global_dir, subject_dir, global_config, subject_config)

    def test_later_release_keeps_configs_despite_persisted_true(
        self, dirs, monkeypatch
    ):
        # A 0.3 file persisting force_pref_reset=true, opened by a later
        # release: neither the global nor the subject configuration is reset.
        global_dir, subject_dir = dirs
        self._global_file(global_dir, swane.__version__, force_pref_reset="true")
        self._subject_file(subject_dir, swane.__version__, force_pref_reset="true")
        self._run_as_version(monkeypatch, swane.__version__ + ".1")

        global_config, subject_config = self._load(global_dir, subject_dir)

        self._assert_kept(global_dir, subject_dir, global_config, subject_config)
        for config in (global_config, subject_config):
            assert config[self.MAIN]["last_swane_version"] == swane.__version__ + ".1"

    def test_newer_version_file_is_kept(self, dirs):
        global_dir, subject_dir = dirs
        self._global_file(global_dir, "99.0")
        self._subject_file(subject_dir, "99.0")

        global_config, subject_config = self._load(global_dir, subject_dir)

        self._assert_kept(global_dir, subject_dir, global_config, subject_config)

    @pytest.mark.parametrize("version", [None, "", "not-a-version"])
    def test_missing_or_invalid_version_is_reset(self, dirs, version):
        global_dir, subject_dir = dirs
        self._global_file(global_dir, version)
        self._subject_file(subject_dir, version)

        global_config, subject_config = self._load(global_dir, subject_dir)

        self._assert_reset(global_dir, subject_dir, global_config, subject_config)

    @pytest.mark.parametrize("flag", ["true", "false"])
    def test_stale_force_pref_reset_option_is_dropped(self, dirs, flag):
        global_dir, subject_dir = dirs
        self._global_file(global_dir, swane.__version__, force_pref_reset=flag)
        self._subject_file(subject_dir, swane.__version__, force_pref_reset=flag)

        global_config, subject_config = self._load(global_dir, subject_dir)

        for config, path in (
            (global_config, global_dir / ".SWANe"),
            (subject_config, subject_dir / ".config"),
        ):
            assert "force_pref_reset" not in config[self.MAIN]
            assert "force_pref_reset" not in self._read(path)[self.MAIN]

    def test_new_subject_config_has_no_force_pref_reset(self, dirs):
        global_dir, subject_dir = dirs
        _, subject_config = self._load(global_dir, subject_dir)
        assert "force_pref_reset" not in subject_config[self.MAIN]
        assert "force_pref_reset" not in GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]


class TestPercentValues:
    """SWANe uses no configparser interpolation: a "%" in any value (folders,
    Slicer extension folders, free text) is stored and read back verbatim."""

    STATE = json.dumps({"revision": "1", "paths": {"A": "/home/u%20x/100%/ext"}})

    def test_slicer_extensions_state_survives_reload(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.set_slicer_extensions_state(self.STATE)
        config.save()

        reloaded = ConfigManager(global_base_folder=str(tmp_path))

        assert reloaded.get_slicer_extensions_state() == self.STATE
        assert self.STATE in (tmp_path / ".SWANe").read_text(encoding="utf-8")

    def test_main_working_directory_survives_reload(self, tmp_path):
        folder = tmp_path / "50%done"
        folder.mkdir()
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.set_main_working_directory(str(folder))

        reloaded = ConfigManager(global_base_folder=str(tmp_path))

        assert reloaded.get_main_working_directory() == str(folder)

    def test_subject_text_value_survives_reload(self, tmp_path):
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        subject_dir = tmp_path / "subj"
        subject_dir.mkdir()
        global_config = ConfigManager(global_base_folder=str(global_dir))
        config = ConfigManager(str(subject_dir), global_config=global_config)
        config[DataInputList.FMRI_0]["task_a_name"] = "Motor 50%"
        config.save()

        reloaded = ConfigManager(str(subject_dir), global_config=global_config)

        assert reloaded[DataInputList.FMRI_0]["task_a_name"] == "Motor 50%"

    def test_hand_edited_percent_is_literal(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.save()
        path = tmp_path / ".SWANe"
        text = path.read_text(encoding="utf-8").replace(
            "default_dicom_folder = dicom", "default_dicom_folder = a%b%(x)s"
        )
        path.write_text(text, encoding="utf-8")

        reloaded = ConfigManager(global_base_folder=str(tmp_path))

        assert reloaded.get_default_dicom_folder() == "a%b%(x)s"

    def test_state_escaped_by_an_older_build_falls_back_to_full_check(self, tmp_path):
        # Builds before this fix stored a "%" of the state as "%%": read
        # verbatim, that folder does not exist, so the full Slicer check runs
        # again and records the state anew.
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        folder = tmp_path / "100%"
        folder.mkdir()
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.save()
        path = tmp_path / ".SWANe"
        escaped = json.dumps({"paths": {"A": str(folder)}}).replace("%", "%%")
        text = path.read_text(encoding="utf-8").replace(
            "slicer_extensions_state = ", "slicer_extensions_state = " + escaped
        )
        path.write_text(text, encoding="utf-8")

        reloaded = ConfigManager(global_base_folder=str(tmp_path))

        assert reloaded.get_slicer_extensions_state() == escaped
        assert (
            SlicerCheckWorker.extensions_state_is_valid(
                reloaded.get_slicer_extensions_state(), ["A"]
            )
            is False
        )


class TestMailManagerFactory:

    def test_disabled_returns_none(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config[GlobalPrefCategoryList.MAIL_SETTINGS]["enabled"] = "false"
        assert config.get_mail_manager() is None

    def test_enabled_returns_manager_with_decrypted_password(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        mail = config[GlobalPrefCategoryList.MAIL_SETTINGS]
        mail["enabled"] = "true"
        mail["address"] = "smtp.example.com"
        mail["port"] = "465"
        mail["username"] = "me@example.com"
        mail["password"] = CryptographyManager.encrypt("secret")

        manager = config.get_mail_manager()
        assert isinstance(manager, MailManager)
        assert manager.password == "secret"
        assert manager.username == "me@example.com"


class TestSubjectConfig:

    def test_subject_config_uses_provided_global_config(self, tmp_path, monkeypatch):
        subject_folder = tmp_path / "subj"
        subject_folder.mkdir()
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        global_config_dir = tmp_path / "global"
        global_config_dir.mkdir()
        global_config = ConfigManager(global_base_folder=str(global_config_dir))
        global_config[GlobalPrefCategoryList.MAIN][
            "default_wf_type"
        ] = WorkflowTypes.FUNCTIONAL.name

        config = ConfigManager(str(subject_folder), global_config=global_config)

        assert config.get_subject_workflow_type() == WorkflowTypes.FUNCTIONAL
        assert not (fake_home / ".SWANe").exists()

        config[DataInputList.T13D]["bet_thr"] = "0.7"
        assert global_config[DataInputList.T13D]["bet_thr"] != "0.7"

    def test_subject_config_structure(self, tmp_path):
        subject_folder = tmp_path / "subj"
        subject_folder.mkdir()
        global_config = ConfigManager(global_base_folder=str(tmp_path))
        config = ConfigManager(str(subject_folder), global_config=global_config)
        assert config.global_config is False
        assert config.config_file == os.path.join(str(subject_folder), ".config")
        assert config.has_section(str(DataInputList.T13D))
        assert config.has_section(str(GlobalPrefCategoryList.MAIN))

    def test_set_workflow_option(self, tmp_path):
        subject_folder = tmp_path / "subj"
        subject_folder.mkdir()
        global_config = ConfigManager(global_base_folder=str(tmp_path))
        config = ConfigManager(str(subject_folder), global_config=global_config)
        config.set_workflow_option(WorkflowTypes.STRUCTURAL)
        assert config[DataInputList.T13D]["wf_type"] == WorkflowTypes.STRUCTURAL.name
        assert config.get_subject_workflow_type() == WorkflowTypes.STRUCTURAL


def test_config_file_is_utf8_with_non_ascii_values(tmp_path):
    """Windows' default text encoding is cp1252: SWANe's own config must be
    written and read as UTF-8 so non-ASCII folders survive a round trip."""
    config = ConfigManager(global_base_folder=str(tmp_path))
    folder = str(tmp_path / "Niccolò Brontë 測試")
    os.makedirs(folder)
    config.set_main_working_directory(folder)
    config.save()

    with open(config.config_file, "rb") as f:
        raw = f.read()
    assert "Niccolò Brontë 測試".encode("utf-8") in raw

    reloaded = ConfigManager(global_base_folder=str(tmp_path))
    assert reloaded.get_main_working_directory() == folder
