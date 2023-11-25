import os
from PySide6.QtWidgets import (QDialog,  QGridLayout, QVBoxLayout, QWidget, QPushButton, QSpacerItem,
                               QSizePolicy, QMessageBox)
from swane import strings
from swane.utils.PreferenceEntry import PreferenceEntry
from swane.utils.wf_preferences import wf_preferences
from swane.ui.VerticalTabWidget import VerticalTabWidget


class WfPreferencesWindow(QDialog):

    def __init__(self, my_config, data_input_list=None, parent=None):
        super(WfPreferencesWindow, self).__init__(parent)

        self.my_config = my_config
        self.restart = False

        if self.my_config.global_config:
            title = strings.wf_pref_window_title_global
        else:
            title = os.path.basename(os.path.dirname(
                self.my_config.config_file)) + strings.wf_pref_window_title_user

        self.setWindowTitle(title)

        self.inputs = {}
        self.input_keys = {}

        layout = QVBoxLayout()

        tab_widget = VerticalTabWidget(200, 25)

        x = 0

        for data_input in data_input_list.values():
            if data_input.name not in my_config:
                continue
            if not my_config.global_config and not data_input.loaded:
                continue

            category = data_input.name
            self.input_keys[category] = {}

            tab = QWidget()
            tab_widget.addTab(tab, data_input.label)
            grid = QGridLayout()
            tab.setLayout(grid)

            for key in my_config[category].keys():
                if key not in wf_preferences[data_input.name]:
                    continue
                self.input_keys[category][key] = x
                self.inputs[x] = PreferenceEntry(category, key, my_config, wf_preferences[data_input.name][key]["input_type"], parent=self)
                self.inputs[x].set_label_text(wf_preferences[data_input.name][key]["label"])
                if wf_preferences[data_input.name][key]["input_type"] == PreferenceEntry.COMBO:
                    self.inputs[x].populate_combo(wf_preferences[data_input.name][key]["default"])
                    self.inputs[x].set_value_from_config(my_config)
                if "tooltip" in wf_preferences[data_input.name][key]:
                    self.inputs[x].set_tooltip(wf_preferences[data_input.name][key]["tooltip"])
                if "range" in wf_preferences[data_input.name][key]:
                    self.inputs[x].set_range(wf_preferences[data_input.name][key]["range"][0], wf_preferences[data_input.name][key]["range"][1])
                self.check_dependency(data_input.name, key, x)
                if "pref_requirement" in wf_preferences[data_input.name][key]:
                    for pref_cat in wf_preferences[data_input.name][key]["pref_requirement"]:
                        if pref_cat not in my_config:
                            continue
                        for pref_req in wf_preferences[data_input.name][key]["pref_requirement"][pref_cat]:
                            if pref_req[0] not in my_config[pref_cat]:
                                continue

                            target_x = self.input_keys[pref_cat][pref_req[0]]
                            if self.inputs[target_x].input_type == PreferenceEntry.CHECKBOX:
                                self.inputs[target_x].input_field.stateChanged.connect(lambda checked, my_cat=data_input.name, my_key=key: self.requirement_changed(checked, my_cat, my_key))
                            elif self.inputs[target_x].input_type == PreferenceEntry.COMBO:
                                self.inputs[target_x].input_field.currentIndexChanged.connect(lambda checked, my_cat=data_input.name, my_key=key: self.requirement_changed(checked, my_cat, my_key))
                            else:
                                self.inputs[target_x].input_field.textChanged.connect(lambda checked, my_cat=data_input.name, my_key=key: self.requirement_changed(checked, my_cat, my_key))
                            if not my_config.getboolean(pref_cat, pref_req[0]):
                                self.inputs[x].disable(wf_preferences[data_input.name][key]["pref_requirement_fail_tooltip"])
                                break
                if not my_config.global_config and 'input_requirement' in wf_preferences[data_input.name][key]:
                    for input_req in wf_preferences[data_input.name][key]['input_requirement']:
                        if not data_input_list[input_req].loaded:
                            self.inputs[x].disable(wf_preferences[data_input.name][key]["input_requirement_fail_tooltip"])
                            break

                grid.addWidget(self.inputs[x].label, x, 0)
                grid.addWidget(self.inputs[x].input_field, x, 1)
                x += 1

            vertical_spacer = QSpacerItem(
                20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
            grid.addItem(vertical_spacer, x, 0, 1, 2)

        layout.addWidget(tab_widget)

        self.saveButton = QPushButton(strings.pref_window_save_button)
        self.saveButton.clicked.connect(self.save_preferences)

        discard_button = QPushButton(strings.pref_window_discard_button)
        discard_button.clicked.connect(self.close)

        reset_button = QPushButton(strings.pref_window_reset_button)
        reset_button.clicked.connect(self.reset)

        layout.addWidget(self.saveButton)
        layout.addWidget(discard_button)
        layout.addWidget(reset_button)

        self.setLayout(layout)

    def check_dependency(self, category, key, x):
        if "dependency" in wf_preferences[category][key]:
            dep_check = getattr(self.my_config, wf_preferences[category][key]["dependency"], None)
            if callable(dep_check) and not dep_check():
                self.inputs[x].disable(wf_preferences[category][key]["dependency_fail_tooltip"])
                return False
        return True

    def requirement_changed(self, checked, my_cat, my_key):
        my_x = self.input_keys[my_cat][my_key]
        if not self.check_dependency(my_cat, my_key, my_x):
            return
        pref_requirement = wf_preferences[my_cat][my_key]["pref_requirement"]
        for req_cat in pref_requirement:
            if req_cat not in self.input_keys:
                continue
            for req_key in pref_requirement[req_cat]:
                if req_key[0] not in self.input_keys[req_cat]:
                    continue
                req_x = self.input_keys[req_cat][req_key[0]]

                if self.inputs[req_x].input_type == PreferenceEntry.CHECKBOX:
                    check = req_key[1] == self.inputs[req_x].input_field.isChecked()
                elif self.inputs[req_x].input_type == PreferenceEntry.COMBO:
                    check = req_key[1] == self.inputs[req_x].input_field.currentIndex()
                else:
                    check = req_key[1] == self.inputs[req_x].input_field.get_value()

                if not check:
                    self.inputs[my_x].disable(wf_preferences[my_cat][my_key]["pref_requirement_fail_tooltip"])
                    return
        self.inputs[my_x].enable()

    def save_preferences(self):
        for pref_entry in self.inputs.values():
            if pref_entry.changed:
                self.my_config[pref_entry.category][pref_entry.key] = pref_entry.get_value()

        self.my_config.save()
        self.done(1)

    def reset(self):
        msg_box = QMessageBox()
        if self.my_config.global_config:
            msg_box.setText(strings.pref_window_reset_global)
        else:
            msg_box.setText(strings.pref_window_reset_pt)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        ret2 = msg_box.exec()

        if ret2 == QMessageBox.StandardButton.Yes:
            self.done(-1)
