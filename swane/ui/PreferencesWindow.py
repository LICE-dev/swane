import os

from PySide6.QtWidgets import (QDialog, QGridLayout, QVBoxLayout, QGroupBox, QPushButton, QHBoxLayout, QLabel)

from swane import strings, EXIT_CODE_REBOOT
from swane.utils.ConfigManager import ConfigManager
from swane.utils.PreferenceEntry import PreferenceEntry
from swane.utils.DataInput import DataInputList


class PreferencesWindow(QDialog):
    """
    Custom implementation of PySide QDialog to show SWANe global preferences.

    """

    def __init__(self, my_config, parent=None):
        super(PreferencesWindow, self).__init__(parent)

        self.my_config = my_config
        self.restart = False

        if self.my_config.global_config:
            title = strings.pref_window_title_global
        else:
            title = os.path.basename(os.path.dirname(
                self.my_config.config_file)) + strings.pref_window_title_user

        self.setWindowTitle(title)

        self.inputs = {}
        self.new_inputs = {}

        main_layout = QHBoxLayout()

        pane = QGroupBox()
        pane.setObjectName("pane")
        layout = QVBoxLayout()
        pane.setLayout(layout)
        pane.setFlat(True)
        pane.setStyleSheet("QGroupBox#pane {border:none;}")

        x = 0
        if self.my_config.global_config:

            group_global = QGroupBox(strings.pref_window_global_box_title)
            grid_global = QGridLayout()
            group_global.setLayout(grid_global)
            x = 0

            category = "MAIN"

            self.new_inputs[x] = PreferenceEntry(category, 'patientsfolder', my_config, PreferenceEntry.DIRECTORY,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_mwd)
            self.new_inputs[x].set_box_text(strings.mainwindow_choose_working_dir_title)
            self.new_inputs[x].restart = True
            grid_global.addWidget(self.new_inputs[x].label, x, 0)
            grid_global.addWidget(self.new_inputs[x].input_field, x, 1)
            grid_global.addWidget(self.new_inputs[x].button, x, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'slicerPath', my_config, PreferenceEntry.FILE, parent=self, validate_on_change=True)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_slicer)
            self.new_inputs[x].set_box_text(strings.pref_window_select_slicer)
            self.new_inputs[x].restart = True
            grid_global.addWidget(self.new_inputs[x].label, x, 0)
            grid_global.addWidget(self.new_inputs[x].input_field, x, 1)
            grid_global.addWidget(self.new_inputs[x].button, x, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'defaultWfType', my_config, PreferenceEntry.COMBO,
                                                 parent=self, populate_combo=ConfigManager.WORKFLOW_TYPES)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_wf)
            grid_global.addWidget(self.new_inputs[x].label, x, 0)
            grid_global.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            layout.addWidget(group_global)

            group_box_performance = QGroupBox(strings.pref_window_performance_box_title)
            grid_performance = QGridLayout()
            group_box_performance.setLayout(grid_performance)
            x = 0

            self.new_inputs[x] = PreferenceEntry(category, 'maxPt', my_config, PreferenceEntry.NUMBER, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_pt_limit)
            self.new_inputs[x].set_range(1, 5)
            grid_performance.addWidget(self.new_inputs[x].label, x, 0)
            grid_performance.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'maxPtCPU', my_config, PreferenceEntry.NUMBER, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_cpu_limit)
            self.new_inputs[x].set_tooltip(strings.pref_window_global_box_cpu_limit_tip)
            self.new_inputs[x].set_range(-1, 40)
            grid_performance.addWidget(self.new_inputs[x].label, x, 0)
            grid_performance.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'bedpostx_core', my_config, PreferenceEntry.COMBO,
                                                 parent=self, populate_combo=ConfigManager.BEDPOSTX_CORES)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_multi_cores)
            grid_performance.addWidget(self.new_inputs[x].label, x, 0)
            grid_performance.addWidget(self.new_inputs[x].input_field, x, 1)
            self.new_inputs[x].input_field.currentIndexChanged.connect(self.update_bedpostx_core_description)
            x += 1
            self.bedpostx_core_description = QLabel()
            self.bedpostx_core_description.setText(strings.pref_window_global_box_multi_cores_description[self.new_inputs[x - 1].input_field.currentIndex()])
            grid_performance.addWidget(self.bedpostx_core_description, x, 0, 1, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'resourceMonitor', my_config, PreferenceEntry.CHECKBOX, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_resource_monitor)
            self.new_inputs[x].set_range(-1, 40)
            grid_performance.addWidget(self.new_inputs[x].label, x, 0)
            grid_performance.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            # Saving in MRML doesn't work well, disable extension choice for now
            # self.new_inputs[x] = PreferenceEntry(category, 'slicerSceneExt', my_config, PreferenceEntry.COMBO,
            #                                      parent=self, populate_combo=PreferencesWindow.SLICER_EXTENSIONS)
            # self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_ext)
            # grid1.addWidget(self.new_inputs[x].label, x, 0)
            # grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            # x += 1

            layout.addWidget(group_box_performance)

            group_box_optional = QGroupBox(strings.pref_window_global_box_optional_title)
            grid_optional = QGridLayout()
            group_box_optional.setLayout(grid_optional)

            category = 'OPTIONAL_SERIES'
            data_input_list = DataInputList()

            for optional_series in my_config[category].keys():
                if optional_series not in data_input_list:
                    continue

                self.new_inputs[x] = PreferenceEntry(category, optional_series, my_config, PreferenceEntry.CHECKBOX,
                                                     parent=self)
                self.new_inputs[x].set_label_text(data_input_list[optional_series].label)
                self.new_inputs[x].restart = True
                grid_optional.addWidget(self.new_inputs[x].label, x, 0)
                grid_optional.addWidget(self.new_inputs[x].input_field, x, 1)
                x += 1

            layout.addWidget(group_box_optional)

        self.saveButton = QPushButton(strings.pref_window_save_button)
        self.saveButton.clicked.connect(self.save_preferences)

        discard_button = QPushButton("Discard changes")
        discard_button.clicked.connect(self.close)

        layout.addWidget(self.saveButton)
        layout.addWidget(discard_button)

        main_layout.addWidget(pane)
        self.setLayout(main_layout)

    def set_restart(self):
        """
        Called when user change a settings that require SWANe restart.

        """
        self.restart = True
        self.saveButton.setText(strings.pref_window_save_restart_button)

    def update_bedpostx_core_description(self, value: int):
        """
        Update the bedpostx core usage setting label if the user change the setting value.
        Parameters
        ----------
        value: int
            The index of the setting combo
        """
        self.bedpostx_core_description.setText(strings.pref_window_global_box_multi_cores_description[value])

    def save_preferences(self):
        """
        Loop all input fields and save values to configuration file.

        """
        for pref_entry in self.new_inputs.values():
            if pref_entry.changed:
                self.my_config[pref_entry.category][pref_entry.key] = pref_entry.get_value()

        self.my_config.save()

        if self.restart:
            ret_code = EXIT_CODE_REBOOT
        else:
            ret_code = 1

        self.done(ret_code)
