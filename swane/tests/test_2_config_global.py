import os
import shutil
from swane.config.ConfigManager import ConfigManager
import pytest
from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.config.config_enums import GlobalPrefCategoryList
from swane.tests import TEST_DIR


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "config")
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)


class TestConfigManager:

    def test_init_global(self, monkeypatch):
        expected_global_config_file = os.path.join(os.getcwd(), ".SWANe")
        if os.path.exists(expected_global_config_file):
            os.remove(expected_global_config_file)

        global_config = ConfigManager(global_base_folder=os.getcwd())
        assert global_config.global_config == True, "global_config False in global ConfigManager init"
        assert global_config.config_file == expected_global_config_file, "global config file name error"
        for category in GlobalPrefCategoryList:
            assert global_config.has_section(str(category)) == True, "Missing global config section"
        # change a random option
        expected_dicom_folder = "testval"
        global_config[GlobalPrefCategoryList.MAIN]['default_dicom_folder'] = expected_dicom_folder
        global_config.save()
        # reload and check
        global_config = ConfigManager(global_base_folder=os.getcwd())
        assert global_config[GlobalPrefCategoryList.MAIN]['default_dicom_folder'] == expected_dicom_folder
        # backup config file, monkeypatch force_pref_reset=true and check if default_dicom_folder is set back to default
        backup_global_config_file = os.path.join(os.getcwd(), ".SWANe_bk")
        shutil.copyfile(global_config.config_file, backup_global_config_file)
        monkeypatch.setattr(GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]['force_pref_reset'], 'default', 'true')
        monkeypatch.setattr(GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]['last_swane_version'], 'default', '0')
        global_config = ConfigManager(global_base_folder=os.getcwd())
        assert global_config[GlobalPrefCategoryList.MAIN]['default_dicom_folder'] == GLOBAL_PREFERENCES[GlobalPrefCategoryList.MAIN]['default_dicom_folder'].default
        monkeypatch.undo()

    def test_main_working_directory(self):
        global_config = ConfigManager(global_base_folder=os.getcwd())

        # try to set a non existing directory
        test_main_working_directory = os.path.join(os.getcwd(), "subjects")
        global_config.set_main_working_directory(test_main_working_directory)
        assert global_config.get_main_working_directory() == "", "Error with non existing main working directory"
        # try to set an existing directory
        os.makedirs(test_main_working_directory)
        global_config.set_main_working_directory(test_main_working_directory)
        assert global_config.get_main_working_directory() == test_main_working_directory, "Error with existing main working directory"















