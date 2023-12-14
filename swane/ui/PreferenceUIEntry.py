import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QDoubleValidator
from PySide6.QtWidgets import (QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox,
                               QComboBox, QStyle, QSizePolicy, QStyleOption)
from enum import Enum
from swane import strings
from swane.config.config_enums import InputTypes
from swane.config.ConfigManager import save_get_int, save_get_float, save_get_boolean, ConfigManager


class PreferenceUIEntry:

    TEXT = 0
    NUMBER = 1
    CHECKBOX = 2
    COMBO = 3
    FILE = 4
    DIRECTORY = 5
    FLOAT = 6
    HIDDEN = 7

    def __init__(self, category: Enum, key: str, my_config: ConfigManager, defaults: dict, input_type=TEXT, restart: bool = False, parent=None, populate_combo: [] = None, validate_on_change: bool = False):
        self.changed = False
        self.category = category
        self.key = key
        self.defaults = defaults
        self.input_type = input_type
        self.restart = restart
        self.parent = parent
        self.tooltip = None
        self.label = QLabel()
        opt = QStyleOption()
        opt.initFrom(self.label)
        text_size = self.label.fontMetrics().size(Qt.TextShowMnemonic, self.label.text())
        height = self.label.style().sizeFromContents(QStyle.CT_PushButton, opt, text_size, self.label).height()
        self.label.setMaximumHeight(height)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.input_field, self.button = self.gen_input_field()
        if input_type == InputTypes.COMBO:
            self.populate_combo(populate_combo)
        self.set_value_from_config(my_config)
        self.box_text = ''
        self.validate_on_change = validate_on_change

    def set_label_text(self, text: str):
        self.label.setText(text)

    def set_box_text(self, text: str):
        self.box_text = text

    def set_changed(self, **kwargs):
        self.changed = True
        if self.restart and self.parent is not None:
            self.parent.set_restart()

    def gen_input_field(self):
        button = None

        if self.input_type == InputTypes.CHECKBOX:
            field = QCheckBox()
            field.toggled.connect(self.set_changed)
        elif self.input_type == InputTypes.COMBO:
            field = QComboBox()
            field.currentIndexChanged.connect(self.set_changed)
        else:
            field = QLineEdit()
            field.textChanged.connect(self.set_changed)

        if self.input_type == InputTypes.NUMBER:
            field.setValidator(QIntValidator(-1, 100))

        if self.input_type == InputTypes.FLOAT:
            validator = QDoubleValidator(0.00, 100.00, 2, field)
            validator.setNotation(QDoubleValidator.StandardNotation)
            field.setValidator(validator)

        if self.input_type == InputTypes.FILE or self.input_type == InputTypes.DIRECTORY:
            field.setReadOnly(True)
            button = QPushButton()
            pixmap = getattr(QStyle, "SP_DirOpenIcon")
            icon_open_dir = button.style().standardIcon(pixmap)
            button.setIcon(icon_open_dir)
            button.clicked.connect(self.choose_file)

        return field, button

    def choose_file(self):
        if self.input_type == InputTypes.FILE:
            file_path, _ = QFileDialog.getOpenFileName(parent=self.parent, caption=self.box_text)
            error = strings.pref_window_file_error
        elif self.input_type == InputTypes.DIRECTORY:
            file_path = QFileDialog.getExistingDirectory(parent=self.parent, caption=self.box_text)
            error = strings.pref_window_dir_error
        else:
            return

        if file_path == '':
            return

        if not os.path.exists(file_path):
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(error)
            msg_box.exec()
            return

        if self.validate_on_change:
            file_path = "*" + file_path

        self.set_value(file_path)

    def populate_combo(self, items: []):
        if self.input_type != InputTypes.COMBO or items is None:
            return
        for index, label in enumerate(items):
            self.input_field.insertItem(index, label)

    def set_value_from_config(self, config: ConfigManager):
        if config is None:
            return

        if self.input_type == InputTypes.CHECKBOX:
            value = save_get_boolean(config, self.defaults, self.category, self.key)
        elif self.input_type == InputTypes.NUMBER or self.input_type == InputTypes.COMBO:
            value = save_get_int(config, self.defaults, self.category, self.key)
        elif self.input_type == InputTypes.FLOAT:
            value = save_get_float(config, self.defaults, self.category, self.key)
        else:
            value = config[self.category][self.key]

        self.set_value(value)

        if str(value).lower() != config[self.category][self.key].lower():
            self.set_changed()

    def set_range(self, min_value: int | float, max_value: int | float):
        if self.input_field.validator() is None:
            return
        if min_value > max_value:
            min_value, max_value = max_value, min_value
        self.input_field.validator().setRange(min_value, max_value)

    def set_value(self, value, reset_change_state: bool = False):
        if self.input_type == InputTypes.CHECKBOX:
            if type(value) is not bool:
                raise Exception("Non boolean value for checkbox: %s" % str(value))
            if value:
                self.input_field.setCheckState(Qt.Checked)
            else:
                self.input_field.setCheckState(Qt.Unchecked)
        elif self.input_type == InputTypes.COMBO:
            if type(value) is not int:
                raise Exception("Non int value for combo")
            self.input_field.setCurrentIndex(value)
        else:
            self.input_field.setText(str(value))

        if reset_change_state:
            self.changed = False

    def disable(self, tooltip: str = None):
        self.input_field.setEnabled(False)
        self.label.setStyleSheet("color: gray")
        self.set_tooltip(tooltip)
        if self.input_type == InputTypes.CHECKBOX:
            self.input_field.setChecked(False)

    def set_tooltip(self, tooltip: str):
        if self.tooltip is None:
            self.tooltip = tooltip
        if tooltip == "" and self.tooltip != "":
            tooltip = self.tooltip
        self.input_field.setToolTip(tooltip)
        self.label.setToolTip(tooltip)
        if tooltip == "":
            self.label.setText(self.label.text().replace(" "+strings.INFOCHAR, ""))
        elif not self.label.text().endswith(strings.INFOCHAR):
            self.label.setText(self.label.text()+" "+strings.INFOCHAR)

    def enable(self):
        self.input_field.setEnabled(True)
        self.set_tooltip(self.tooltip)
        self.label.setStyleSheet("")

    def get_value(self) -> str:
        if self.input_type == InputTypes.COMBO:
            value = str(self.input_field.currentIndex())
        elif self.input_type == InputTypes.CHECKBOX:
            if self.input_field.checkState() == Qt.Checked:
                value = 'true'
            else:
                value = "false"
        else:
            value = self.input_field.text()

        return value

