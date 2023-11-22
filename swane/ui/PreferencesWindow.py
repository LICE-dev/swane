import os

from PySide6.QtWidgets import (QDialog, QGridLayout, QVBoxLayout, QGroupBox, QPushButton, QHBoxLayout, QLabel)

from swane import strings, EXIT_CODE_REBOOT
from swane.utils.ConfigManager import ConfigManager
from swane.utils.PreferenceEntry import PreferenceEntry
from swane.utils.DataInput import DataInputList


class PreferencesWindow(QDialog):

    def __init__(self, my_config, data_input_list=None, parent=None):
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

        layout = QHBoxLayout()

        pane = QGroupBox()
        pane.setObjectName("pane")
        layout = QVBoxLayout()
        pane.setLayout(layout)
        pane.setFlat(True)
        pane.setStyleSheet("QGroupBox#sn_pane {border:none;}")

        x = 0
        if self.my_config.global_config:

            group_box1 = QGroupBox(strings.pref_window_global_box_title)
            grid1 = QGridLayout()
            group_box1.setLayout(grid1)
            x = 0

            category = "MAIN"

            self.new_inputs[x] = PreferenceEntry(category, 'patientsfolder', my_config, PreferenceEntry.DIRECTORY,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_mwd)
            self.new_inputs[x].set_box_text(strings.mainwindow_choose_working_dir_title)
            self.new_inputs[x].restart = True
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            grid1.addWidget(self.new_inputs[x].button, x, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'slicerPath', my_config, PreferenceEntry.FILE, parent=self, validate_on_change=True)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_slicer)
            self.new_inputs[x].set_box_text(strings.pref_window_select_slicer)
            self.new_inputs[x].restart = True
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            grid1.addWidget(self.new_inputs[x].button, x, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'defaultWfType', my_config, PreferenceEntry.COMBO,
                                                 parent=self, populate_combo=ConfigManager.WORKFLOW_TYPES)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_wf)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'maxPt', my_config, PreferenceEntry.NUMBER, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_pt_limit)
            self.new_inputs[x].set_range(1, 5)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'maxPtCPU', my_config, PreferenceEntry.NUMBER, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_cpu_limit)
            self.new_inputs[x].set_range(-1, 40)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'bedpostx_core', my_config, PreferenceEntry.COMBO,
                                                 parent=self, populate_combo=ConfigManager.BEDPOSTX_CORES)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_bedpostx_cores)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            self.new_inputs[x].input_field.currentIndexChanged.connect(self.update_bedpostx_core_description)
            x += 1
            self.bedpostx_core_description = QLabel()
            self.bedpostx_core_description.setText(strings.pref_window_global_box_bedpostx_description[self.new_inputs[x-1].input_field.currentIndex()])
            grid1.addWidget(self.bedpostx_core_description, x, 0, 1, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'resourceMonitor', my_config, PreferenceEntry.CHECKBOX, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_resource_monitor)
            self.new_inputs[x].set_range(-1, 40)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            # Saving in MRML doesn't work well, disable extension choice for now
            # self.new_inputs[x] = PreferenceEntry(category, 'slicerSceneExt', my_config, PreferenceEntry.COMBO,
            #                                      parent=self, populate_combo=PreferencesWindow.SLICER_EXTENSIONS)
            # self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_ext)
            # grid1.addWidget(self.new_inputs[x].label, x, 0)
            # grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            # x += 1

            layout.addWidget(group_box1)

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

        if self.my_config.global_config:
            layout.addWidget(pane)
            layout.addWidget(self.saveButton)
            layout.addWidget(discard_button)

        self.setLayout(layout)

    def set_restart(self):
        self.restart = True
        self.saveButton.setText(strings.pref_window_save_restart_button)

    def update_bedpostx_core_description(self, value):
        self.bedpostx_core_description.setText(strings.pref_window_global_box_bedpostx_description[value])

    def save_preferences(self):
        for pref_entry in self.new_inputs.values():
            if pref_entry.changed:
                self.my_config[pref_entry.category][pref_entry.key] = pref_entry.get_value()

        self.my_config.save()

        if self.restart:
            ret_code = EXIT_CODE_REBOOT
        else:
            ret_code = 1

        self.done(ret_code)
