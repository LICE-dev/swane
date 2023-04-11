import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox,
                               QComboBox, QStyle, QSizePolicy)

from swane import strings
from configparser import RawConfigParser


class PreferenceEntry:

    TEXT = 0
    NUMBER = 1
    CHECKBOX = 2
    COMBO = 3
    FILE = 4
    DIRECTORY = 5

    def __init__(self, category, key, my_config, input_type=TEXT, parent=None, populate_combo=None):
        self.restart = False
        self.category = category
        self.key = key
        self.input_type = input_type
        self.label = QLabel()
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.input_field, self.button = self.gen_input_field()
        if input_type == PreferenceEntry.COMBO and populate_combo is not None:
            self.populate_combo(populate_combo)
        self.set_value_from_config(my_config)
        self.box_text = ''
        self.parent = parent
        self.changed = False

    def set_label_text(self, text):
        self.label.setText(text)

    def set_box_text(self, text):
        self.box_text = text

    def set_changed(self, **kwargs):
        self.changed = True
        if self.restart and self.parent is not None:
            self.parent.set_restart()

    def gen_input_field(self):
        button = None

        if self.input_type == PreferenceEntry.CHECKBOX:
            field = QCheckBox()
            field.toggled.connect(self.set_changed)
        elif self.input_type == PreferenceEntry.COMBO:
            field = QComboBox()
            field.currentIndexChanged.connect(self.set_changed)
        else:
            field = QLineEdit()
            field.textChanged.connect(self.set_changed)

        if self.input_type == PreferenceEntry.NUMBER:
            field.setValidator(QIntValidator(-1, 100))

        if self.input_type == PreferenceEntry.FILE or self.input_type == PreferenceEntry.DIRECTORY:
            field.setReadOnly(True)
            button = QPushButton()
            pixmap = getattr(QStyle, "SP_DirOpenIcon")
            icon_open_dir = button.style().standardIcon(pixmap)
            button.setIcon(icon_open_dir)
            button.clicked.connect(self.chose_file)

        return field, button

    def chose_file(self, parent):
        print("mah")
        if self.input_type == PreferenceEntry.FILE:
            file_path, _ = QFileDialog.getOpenFileName(parent=self.parent, caption=self.box_text)
            error = strings.pref_window_file_error
        elif self.input_type == PreferenceEntry.DIRECTORY:
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
        self.set_value(file_path)

    def populate_combo(self, items):
        if self.input_type != PreferenceEntry.COMBO:
            return
        for index, label in enumerate(items):
            self.input_field.insertItem(index, label)

    def set_value_from_config(self, config):
        try:
            self.set_value(config[self.category][self.key])
        except:
            pass

    def set_range(self, min_value: int, max_value: int):
        if self.input_type != PreferenceEntry.NUMBER:
            return
        if min_value > max_value:
            x = min_value
            min_value = max_value
            max_value = x
        self.input_field.setValidator(QIntValidator(min_value, max_value))

    def set_value(self, value, reset_change_state=False):
        if self.input_type == PreferenceEntry.CHECKBOX:
            if value in RawConfigParser.BOOLEAN_STATES and RawConfigParser.BOOLEAN_STATES[value]:
                self.input_field.setCheckState(Qt.Checked)
            else:
                self.input_field.setCheckState(Qt.Unchecked)
        elif self.input_type == PreferenceEntry.COMBO:
            try:
                self.input_field.setCurrentIndex(int(value))
            except ValueError:
                index = self.input_field.findText(value)
                if index != -1:
                    self.input_field.setCurrentIndex(index)
                else:
                    return
        else:
            self.input_field.setText(value)

        if reset_change_state:
            self.changed = False

    def disable(self, tooltip=None):
        self.input_field.setEnabled(False)
        self.label.setStyleSheet("color: gray")
        if tooltip is not None:
            self.input_field.setToolTip(tooltip)
            self.label.setToolTip(tooltip)
        if self.input_type == PreferenceEntry.CHECKBOX:
            self.input_field.setChecked(False)

    def enable(self):
        self.input_field.setEnabled(True)
        self.label.setToolTip(None)
        self.label.setStyleSheet("")

    def get_value(self):
        if self.input_type == PreferenceEntry.COMBO:
            value = str(self.input_field.currentIndex())
        elif self.input_type == PreferenceEntry.CHECKBOX:
            if self.input_field.checkState() == Qt.Checked:
                value = 'true'
            else:
                value = "false"
        else:
            value = self.input_field.text()

        return value

