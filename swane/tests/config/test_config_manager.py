"""Unit tests for :class:`swane.config.ConfigManager.ConfigManager`."""

import os
import shutil

import pytest

from swane.config.ConfigManager import ConfigManager
from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.config.config_enums import (
    GlobalPrefCategoryList,
    PerformanceProfile,
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

    def test_force_pref_reset_restores_defaults(self, tmp_path, monkeypatch):
        # A reset is triggered only when the file was written by a different
        # SWANe version, so we persist an old last_swane_version on disk.
        config = ConfigManager(global_base_folder=str(tmp_path))
        config[GlobalPrefCategoryList.MAIN]["default_dicom_folder"] = "changed"
        config[GlobalPrefCategoryList.MAIN]["last_swane_version"] = "0.0.0"
        config.save()

        monkeypatch.setattr(
            GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]["force_pref_reset"],
            "default",
            "true",
        )
        reset = ConfigManager(global_base_folder=str(tmp_path))
        assert (
            reset[GlobalPrefCategoryList.MAIN]["default_dicom_folder"]
            == GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN][
                "default_dicom_folder"
            ].default
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

    def test_scene_ext_and_default_dicom_folder(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        assert config.get_slicer_scene_ext() in ("mrb", "mrml")
        assert config.get_default_dicom_folder() != ""

    def test_apply_resource_profile(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.apply_resource_profile(PerformanceProfile.LOW_RESOURCE)
        assert config[GlobalPrefCategoryList.PERFORMANCE]["max_subj"] == "1"
        config.apply_resource_profile(PerformanceProfile.MAX_PERF)
        assert config[GlobalPrefCategoryList.PERFORMANCE]["max_subj"] == "3"


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

    def test_subject_config_structure(self, tmp_path):
        subject_folder = tmp_path / "subj"
        subject_folder.mkdir()
        config = ConfigManager(str(subject_folder))
        assert config.global_config is False
        assert config.config_file == os.path.join(str(subject_folder), ".config")
        assert config.has_section(str(DataInputList.T13D))
        assert config.has_section(str(GlobalPrefCategoryList.MAIN))

    def test_set_workflow_option(self, tmp_path):
        subject_folder = tmp_path / "subj"
        subject_folder.mkdir()
        config = ConfigManager(str(subject_folder))
        config.set_workflow_option(WorkflowTypes.STRUCTURAL)
        assert config[DataInputList.T13D]["wf_type"] == WorkflowTypes.STRUCTURAL.name
        assert config.get_subject_workflow_type() == WorkflowTypes.STRUCTURAL
