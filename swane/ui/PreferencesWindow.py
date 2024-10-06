from datetime import datetime
from functools import partial
import os
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QMessageBox,
)
from swane import strings, EXIT_CODE_REBOOT
from swane.ui.PreferenceUIEntry import PreferenceUIEntry
from swane.config.preference_list import WF_PREFERENCES, GLOBAL_PREFERENCES
from PySide6_VerticalQTabWidget import VerticalQTabWidget
from swane.config.config_enums import InputTypes, GlobalPrefCategoryList
from swane.utils.DataInputList import DataInputList
from enum import Enum
from swane.utils.CryptographyManager import CryptographyManager

from swane.utils.MailManager import MailManager


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
                title = strings.menu_wf_pref
                self.preferences = WF_PREFERENCES
            else:
                title = strings.menu_pref
                self.preferences = GLOBAL_PREFERENCES
        else:
            self.preferences = WF_PREFERENCES
            title = (
                os.path.basename(os.path.dirname(self.my_config.config_file))
                + strings.wf_pref_window_title_user
            )

        if is_workflow:
            default_pref_list = DataInputList
        else:
            default_pref_list = GlobalPrefCategoryList

        self.setWindowTitle(title)

        self.inputs = {}
        self.input_keys = {}

        layout = QVBoxLayout()

        tab_widget = VerticalQTabWidget(force_top_valign=True)

        x = 0

        # Define here to prevent calling during invalid pref value reading
        self.saveButton = QPushButton(strings.pref_window_save_button)
        self.saveButton.clicked.connect(self.save_preferences)

        for category in default_pref_list:
            if str(category) not in my_config:
                continue
            if (
                is_workflow
                and not my_config.global_config
                and not self.parent().subject.input_state_list[category].loaded
            ):
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
                if self.preferences[category][key].hidden:
                    continue
                self.input_keys[category][key] = x
                self.inputs[x] = PreferenceUIEntry(
                    category=category,
                    key=key,
                    my_config=my_config,
                    entry=self.preferences[category][key],
                    parent=self,
                )
                # External dependencies check
                self.check_dependency(category, key, x)

                # Other preferences requirements
                if self.preferences[category][key].pref_requirement is not None:
                    # Search all inputs that are preference for this one and apply them a function on change
                    for pref_cat in self.preferences[category][key].pref_requirement:
                        if str(pref_cat) not in my_config:
                            continue
                        for pref_req in self.preferences[category][key].pref_requirement[pref_cat]:
                            if str(pref_req[0]) not in my_config[pref_cat]:
                                continue
                            target_x = self.input_keys[pref_cat][pref_req[0]]
                            self.inputs[target_x].connect_change(
                                lambda checked, my_cat=category, my_key=key: self.requirement_changed(
                                    checked, my_cat, my_key
                                )
                            )
                    # After the loop check if pref should be enabled
                    self.requirement_changed(False, category, key)

                # Data input requirements
                if (
                    not my_config.global_config
                    and self.preferences[category][key].input_requirement is not None
                ):
                    for input_req in self.preferences[category][key].input_requirement:
                        for cat_check in default_pref_list:
                            if (
                                cat_check == input_req
                                and not self.parent()
                                .subject.input_state_list[cat_check]
                                .loaded
                            ):
                                self.inputs[x].disable(
                                    self.preferences[category][
                                        key
                                    ].input_requirement_fail_tooltip
                                )
                                break

                # Add GUI elements to grid
                grid.addWidget(self.inputs[x].label, x, 0)
                grid.addWidget(self.inputs[x].input_field, x, 1)
                if self.inputs[x].button is not None:
                    grid.addWidget(self.inputs[x].button, x, 2)
                x += 1

                # Informative text displayed in next row, if present
                if self.inputs[x - 1].informative_text_label is not None:
                    grid.addWidget(
                        self.inputs[x - 1].informative_text_label, x, 0, 1, 2
                    )
                    x += 1

            vertical_spacer = QSpacerItem(
                20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding
            )
            grid.addItem(vertical_spacer, x, 0, 1, 2)

            if category is GlobalPrefCategoryList.MAIL_SETTINGS:
                x += 1
                test_button = QPushButton()
                test_button.setText(strings.pref_window_mail_test_button)
                test_button.setToolTip(strings.pref_window_mail_test_hint)

                test_button.clicked.connect(self.send_test_mail)

                grid.addWidget(test_button, x, 0, 1, 2)

        layout.addWidget(tab_widget)
        layout.addWidget(self.saveButton)

        discard_button = QPushButton(strings.pref_window_discard_button)
        discard_button.clicked.connect(self.close)
        layout.addWidget(discard_button)

        if self.preferences != GLOBAL_PREFERENCES:
            reset_button = QPushButton()
            if self.my_config.global_config:
                reset_button.setText(strings.pref_window_reset_global_button)
            else:
                reset_button.setText(strings.pref_window_reset_subj_button)
            reset_button.clicked.connect(self.reset)
            layout.addWidget(reset_button)

        self.setLayout(layout)

    def send_test_mail(self):
        try:
            server_address = self.inputs[self.input_keys[GlobalPrefCategoryList.MAIL_SETTINGS]["address"]].get_value()
            port = self.inputs[self.input_keys[GlobalPrefCategoryList.MAIL_SETTINGS]["port"]].get_value()
            username = self.inputs[self.input_keys[GlobalPrefCategoryList.MAIL_SETTINGS]["username"]].get_value()
            password = CryptographyManager.decrypt(self.inputs[self.input_keys[GlobalPrefCategoryList.MAIL_SETTINGS]["password"]].get_value())
            use_ssl = self.inputs[self.input_keys[GlobalPrefCategoryList.MAIL_SETTINGS]["use_ssl"]].get_value()
            use_tls = self.inputs[self.input_keys[GlobalPrefCategoryList.MAIL_SETTINGS]["use_tls"]].get_value()

            if server_address == "" or port == "" or username == "" or password == "":
                raise Exception("Fill all mail configuration fields first")

            mail_manager = MailManager(
                server_address, port, username, password, use_ssl, use_tls
            )

            mail_manager.send_report(
                f"This is a test mail sent by SWANe at {datetime.now()} to check the mail settings configuration inserted by the user"
            )
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(strings.pref_window_mail_test_success)
            msg_box.setWindowTitle("Mail report")
            msg_box.exec()
        except Exception as e:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setText(strings.pref_window_mail_test_fail)
            msg_box.setInformativeText(str(e))
            msg_box.setWindowTitle("Mail report")
            msg_box.exec()

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
            dep_check = getattr(
                self.dependency_manager,
                self.preferences[category][key].dependency,
                None,
            )
            if dep_check is None or not callable(dep_check) or not dep_check():
                self.inputs[x].disable(
                    self.preferences[category][key].dependency_fail_tooltip
                )
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

                if self.inputs[req_x].input_type == InputTypes.BOOLEAN:
                    check = req_key[1] == self.inputs[req_x].input_field.isChecked()
                elif self.inputs[req_x].input_type == InputTypes.ENUM:
                    check = req_key[1].name == self.inputs[req_x].input_field.itemData(self.inputs[req_x].input_field.currentIndex()).name
                else:
                    check = req_key[1] == self.inputs[req_x].input_field.get_value()

                if not check:
                    self.inputs[my_x].disable(
                        self.preferences[my_cat][my_key].pref_requirement_fail_tooltip
                    )
                    return
        self.inputs[my_x].enable()

    def save_preferences(self):
        """
        Loop all input fields and save values to configuration file.

        """
        for pref_entry in self.inputs.values():
            if pref_entry.changed:
                self.my_config[pref_entry.category][
                    pref_entry.key
                ] = pref_entry.get_value()

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
            msg_box.setText(strings.pref_window_reset_subj_box)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
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
