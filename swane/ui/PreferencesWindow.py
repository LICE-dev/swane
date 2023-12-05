import os
from PySide6.QtWidgets import (QDialog,  QGridLayout, QVBoxLayout, QWidget, QPushButton, QSpacerItem,
                               QSizePolicy, QMessageBox, QLabel)
from swane import strings, EXIT_CODE_REBOOT
from swane.ui.PreferenceUIEntry import PreferenceUIEntry
from swane.config.preference_list import WF_PREFERENCES, GLOBAL_PREFERENCES
from swane.config.GlobalPrefCategoryList import GlobalPrefCategoryList
from PySide6_VerticalQTabWidget import VerticalQTabWidget
from swane.config.config_enums import InputTypes
from swane.utils.DataInputList import DataInputList
from enum import Enum


class PreferencesWindow(QDialog):
    """
    Custom implementation of PySide QDialog to show SWANe workflow preferences.

    """

    def __init__(self, my_config, dependency_manager, is_workflow: bool, parent=None):
        super(PreferencesWindow, self).__init__(parent)

        self.my_config = my_config
        self.dependency_manager = dependency_manager
        self.restart = False

        if self.my_config.global_config:
            if is_workflow:
                title = strings.wf_pref_window_title_global
                self.preferences = WF_PREFERENCES
            else:
                title = strings.pref_window_title_global
                self.preferences = GLOBAL_PREFERENCES
        else:
            self.preferences = WF_PREFERENCES
            title = os.path.basename(os.path.dirname(
                self.my_config.config_file)) + strings.wf_pref_window_title_user

        if is_workflow:
            default_pref_list = DataInputList
        else:
            default_pref_list = GlobalPrefCategoryList

        self.setWindowTitle(title)

        self.inputs = {}
        self.input_keys = {}

        layout = QVBoxLayout()

        tab_widget = VerticalQTabWidget()

        x = 0

        for category in default_pref_list:

            if str(category) not in my_config:
                continue

            if is_workflow and not my_config.global_config and not self.parent().patient.input_state_list[category].loaded:
                continue

            cat_label = category.value.label

            self.input_keys[category] = {}

            tab = QWidget()
            tab_widget.addTab(tab, cat_label)
            grid = QGridLayout()
            tab.setLayout(grid)

            for key in my_config[category].keys():
                if key not in self.preferences[category]:
                    continue
                if self.preferences[category][key].input_type == InputTypes.HIDDEN:
                    continue
                self.input_keys[category][key] = x
                self.inputs[x] = PreferenceUIEntry(category, key, my_config, self.preferences[category][key].input_type, parent=self)

                # Label and Tooltip
                self.inputs[x].set_label_text(self.preferences[category][key].label)
                self.inputs[x].set_tooltip(self.preferences[category][key].tooltip)

                # Some global preference need application restart
                self.inputs[x].restart = self.preferences[category][key].restart

                # Input type-related controls
                if self.preferences[category][key].input_type == InputTypes.COMBO:
                    self.inputs[x].populate_combo(self.preferences[category][key].default)
                    self.inputs[x].set_value_from_config(my_config)
                elif self.preferences[category][key].input_type == InputTypes.FILE or self.preferences[category][key].input_type == InputTypes.DIRECTORY:
                    grid.addWidget(self.inputs[x].button, x, 2)
                    # path validation for folders and file
                    self.inputs[x].validate_on_change = self.preferences[category][key].validate_on_change

                # Range application
                if self.preferences[category][key].range is not None:
                    self.inputs[x].set_range(self.preferences[category][key].range[0], self.preferences[category][key].range[1])

                # External dependence check
                self.check_dependency(category, key, x)

                # Other preference requirement
                if self.preferences[category][key].pref_requirement is not None:
                    for pref_cat in self.preferences[category][key].pref_requirement:
                        if str(pref_cat) not in my_config:
                            continue
                        for pref_req in self.preferences[category][key].pref_requirement[pref_cat]:
                            if str(pref_req[0]) not in my_config[pref_cat]:
                                continue
                            target_x = self.input_keys[pref_cat][pref_req[0]]
                            if self.inputs[target_x].input_type == InputTypes.CHECKBOX:
                                self.inputs[target_x].input_field.stateChanged.connect(lambda checked, my_cat=category, my_key=key: self.requirement_changed(checked, my_cat, my_key))
                            elif self.inputs[target_x].input_type == InputTypes.COMBO:
                                self.inputs[target_x].input_field.currentIndexChanged.connect(lambda checked, my_cat=category, my_key=key: self.requirement_changed(checked, my_cat, my_key))
                            else:
                                self.inputs[target_x].input_field.textChanged.connect(lambda checked, my_cat=category, my_key=key: self.requirement_changed(checked, my_cat, my_key))
                            if not my_config.getboolean(pref_cat, pref_req[0]):
                                self.inputs[x].disable(self.preferences[category][key].pref_requirement_fail_tooltip)
                                break
                if not my_config.global_config and self.preferences[category][key].input_requirement is not None:
                    for input_req in self.preferences[category][key].input_requirement:
                        for cat_check in default_pref_list:
                            if cat_check == input_req and not self.parent().patient.input_state_list[cat_check].loaded:
                                self.inputs[x].disable(self.preferences[category][key].input_requirement_fail_tooltip)
                                break

                grid.addWidget(self.inputs[x].label, x, 0)
                grid.addWidget(self.inputs[x].input_field, x, 1)
                x += 1

                # Informative text displayed in next row
                if self.preferences[category][key].informative_text is not None:
                    informative_text_label = QLabel()
                    informative_text_label.setText(self.preferences[category][key].informative_text[
                                                               self.inputs[x - 1].input_field.currentIndex()])
                    grid.addWidget(informative_text_label, x, 0, 1, 2)
                    self.inputs[x-1].input_field.currentIndexChanged.connect(lambda value,
                                                                                    q_label=informative_text_label,
                                                                                    labels=self.preferences[category][key].informative_text:
                                                                             PreferencesWindow.update_informative_text(value, q_label, labels))
                    x += 1

            vertical_spacer = QSpacerItem(
                20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
            grid.addItem(vertical_spacer, x, 0, 1, 2)

        layout.addWidget(tab_widget)

        self.saveButton = QPushButton(strings.pref_window_save_button)
        self.saveButton.clicked.connect(self.save_preferences)
        layout.addWidget(self.saveButton)

        discard_button = QPushButton(strings.pref_window_discard_button)
        discard_button.clicked.connect(self.close)
        layout.addWidget(discard_button)

        if self.preferences != GLOBAL_PREFERENCES:
            reset_button = QPushButton()
            if self.my_config.global_config:
                reset_button.setText(strings.pref_window_reset_global_button)
            else:
                reset_button.setText(strings.pref_window_reset_pt_button)
            reset_button.clicked.connect(self.reset)
            layout.addWidget(reset_button)

        self.setLayout(layout)

    def check_dependency(self, category: Enum, key: str, x: int) -> bool:
        """
        Check an external dependence to test if a preference can be enabled.
        Parameters
        ----------
        category: Enum
            The category of the preference to be tested.
        key: str
            The name of the preference to be tested.
        x: int
            The index of the preference to be tested in the input field list.

        Return
        ----------
        True if external dependence is satisfied
        """
        if self.preferences[category][key].dependency is not None:
            dep_check = getattr(self.dependency_manager, self.preferences[category][key].dependency, None)
            if dep_check is None or not callable(dep_check) or not dep_check():
                self.inputs[x].disable(self.preferences[category][key].dependency_fail_tooltip)
                return False
        return True

    def requirement_changed(self, checked, my_cat: str, my_key: str):
        """
        Called if the user change a preference that is a requirement for another preference.
        Parameters
        ----------
        checked:
            Unused but passed by the event connection.
        my_cat: str
            The category of the preference to be tested.
        my_key: str
            The name of the preference to be tested.

        """
        my_x = self.input_keys[my_cat][my_key]
        if not self.check_dependency(my_cat, my_key, my_x):
            return
        pref_requirement = self.preferences[my_cat][my_key].pref_requirement
        for req_cat in pref_requirement:
            if req_cat not in self.input_keys:
                continue
            for req_key in pref_requirement[req_cat]:
                if req_key[0] not in self.input_keys[req_cat]:
                    continue
                req_x = self.input_keys[req_cat][req_key[0]]

                if self.inputs[req_x].input_type == InputTypes.CHECKBOX:
                    check = req_key[1] == self.inputs[req_x].input_field.isChecked()
                elif self.inputs[req_x].input_type == InputTypes.COMBO:
                    check = req_key[1] == self.inputs[req_x].input_field.currentIndex()
                else:
                    check = req_key[1] == self.inputs[req_x].input_field.get_value()

                if not check:
                    self.inputs[my_x].disable(self.preferences[my_cat][my_key].pref_requirement_fail_tooltip)
                    return
        self.inputs[my_x].enable()

    def save_preferences(self):
        """
        Loop all input fields and save values to configuration file.

        """
        for pref_entry in self.inputs.values():
            if pref_entry.changed:
                self.my_config[pref_entry.category][pref_entry.key] = pref_entry.get_value()

        self.my_config.save()
        if self.restart:
            ret_code = EXIT_CODE_REBOOT
        else:
            ret_code = 1

        self.done(ret_code)

    def reset(self):
        """
        Load default workflow settings and save them to the configuration file

        """
        msg_box = QMessageBox()
        if self.my_config.global_config:
            msg_box.setText(strings.pref_window_reset_global_box)
        else:
            msg_box.setText(strings.pref_window_reset_pt_box)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        ret2 = msg_box.exec()

        if ret2 == QMessageBox.StandardButton.Yes:
            self.done(-1)

    def set_restart(self):
        """
        Called when user change a settings that require SWANe restart.

        """
        self.restart = True
        self.saveButton.setText(strings.pref_window_save_restart_button)

    @staticmethod
    def update_informative_text(value: int, q_label: QLabel, labels: list):
        """
        Update the bedpostx core usage setting label if the user change the setting value.
        Parameters
        ----------
        value: int
            The index of the setting combo
        q_label: int
            The QLabel to update
        labels: list
            The list of possible labels
        """
        q_label.setText(labels[value])
