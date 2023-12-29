import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QDoubleValidator
from PySide6.QtWidgets import (QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox,
                               QComboBox, QStyle, QSizePolicy, QStyleOption, QWidget)
from enum import Enum
from swane import strings
from swane.config.config_enums import InputTypes
from swane.config.ConfigManager import ConfigManager
from swane.config.PreferenceEntry import PreferenceEntry


class PreferenceUIEntry:
    """
        This class manage The label and the input of a preference based on the value of a PreferenceEntry
    """

    def __init__(self, category: Enum, key: str, my_config: ConfigManager, entry: PreferenceEntry, parent=None):

        # Var initialization
        self.changed = False
        self.category = category
        self.key = key
        self.parent = parent
        self.label = QLabel()
        self.tooltip = None
        opt = QStyleOption()
        opt.initFrom(self.label)
        text_size = self.label.fontMetrics().size(Qt.TextShowMnemonic, self.label.text())
        height = self.label.style().sizeFromContents(QStyle.CT_PushButton, opt, text_size, self.label).height()
        self.label.setMaximumHeight(height)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.box_text = ''

        # Import values from entry
        self.input_type = entry.input_type
        self.restart = entry.restart
        self.informative_text = entry.informative_text
        self.input_field, self.button = self.gen_input_field()
        self.informative_text_label = self.gen_informative_text_label()
        if self.input_type == InputTypes.ENUM and entry.value_enum is not None:
            self.populate_combo(entry.value_enum)
        self.validate_on_change = entry.validate_on_change

        # Apply values to GUI elements
        self.set_value_from_config(my_config)
        self.set_label_text(entry.label)
        self.set_tooltip(entry.tooltip)
        self.set_informative_text()
        if entry.range is not None:
            self.set_range(entry.range[0], entry.range[1])

        # Change-connect must be the last step, otherwise it is fired during initialization
        self.connect_change(self.set_changed)

    def set_label_text(self, text: str):
        self.label.setText(text)

    def set_box_text(self, text: str):
        self.box_text = text

    def set_changed(self, **kwargs):
        """
        Fired when the input value is changed.
        Used for config saving and eventual application restart
        """
        self.changed = True
        if self.restart and self.parent is not None:
            self.parent.set_restart()

    def connect_change(self, callback_function: callable):
        """
        Connect the input field to a callback function

        Parameters
        ----------
        callback_function: callable
            The function to connect
        """
        if callback_function is None:
            return
        if self.input_type == InputTypes.BOOLEAN:
            self.input_field.toggled.connect(callback_function)
        elif self.input_type == InputTypes.ENUM:
            self.input_field.currentIndexChanged.connect(callback_function)
        else:
            self.input_field.textChanged.connect(callback_function)

    def gen_informative_text_label(self) -> QLabel:
        """
        Generate a QLabel to display informative text related to current preference value

        Return
        ----------
        The QLabel
        """
        informative_text_label = None
        if self.informative_text is not None:
            informative_text_label = QLabel()
            self.connect_change(self.set_informative_text)
        return informative_text_label

    def set_informative_text(self, **kwargs):
        """
        Update the informative_text_label when the preference value is changed
        """
        if self.informative_text_label is None or self.informative_text is None:
            return
        if self.get_typed_value() not in self.informative_text:
            return
        self.informative_text_label.setText(self.informative_text[self.get_typed_value()])

    def gen_input_field(self) -> [QWidget, QPushButton]:
        """
        Generate an input field using a widget based on preference type and, if required, a button to open a file selector

        Return
        ----------
        The input field widget and the button
        """
        button = None

        if self.input_type == InputTypes.BOOLEAN:
            field = QCheckBox()
        elif self.input_type == InputTypes.ENUM:
            field = QComboBox()
        else:
            field = QLineEdit()

        if self.input_type == InputTypes.INT:
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
        """
        Open a selection window to chose a file ora directory
        """
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

    def populate_combo(self, items: Enum):
        """
        In case of QComboBox, populates it using an Enum members.
        Each Enum member is stored in menu Data and it's value is used as label

        Parameters
        ----------
        items: Enum
            The Enum iterated to populate the ComboBox

        """
        if self.input_type != InputTypes.ENUM or items is None:
            return
        for member in items:
            self.input_field.addItem(member.value, userData=member)

    def set_value_from_config(self, config: ConfigManager):
        """
        Get the value of a preference forcing it's type based on self.input_type

        Parameters
        ----------
        config: ConfigManager
           The configuration from which read the value

        """
        if config is None:
            return

        if self.input_type == InputTypes.BOOLEAN:
            value = config.getboolean_safe(self.category, self.key)
        elif self.input_type == InputTypes.INT:
            value = config.getint_safe(self.category, self.key)
        elif self.input_type == InputTypes.ENUM:
            value = config.getenum_safe(self.category, self.key)
        elif self.input_type == InputTypes.FLOAT:
            value = config.getfloat_safe(self.category, self.key)
        else:
            value = config[self.category][self.key]

        self.set_value(value)

        # Convert Enum to their label for compare reason
        if hasattr(value, "name"):
            value = value.name
        if str(value).lower() != config[self.category][self.key].lower():
            self.set_changed()

    def set_range(self, min_value, max_value):
        """
        Apply specified values to a numeric input field validator

        Parameters
        ----------
        min_value: int or float
            The minimum accepted value
        max_value: int or float
           The maximum accepted value
        """
        if self.input_field.validator() is None:
            return
        if min_value > max_value:
            min_value, max_value = max_value, min_value
        self.input_field.validator().setRange(min_value, max_value)

    def set_value(self, value, reset_change_state: bool = False):
        """
        Insert a value in the input field

        Parameters
        ----------
        value
            The new value to be displayed
        reset_change_state: bool, optional
           If True, the field change status will not be set to True. Default is False.
        """
        if self.input_type == InputTypes.BOOLEAN:
            if type(value) is not bool:
                raise Exception("Non boolean value for checkbox: %s" % str(value))
            if value:
                self.input_field.setCheckState(Qt.Checked)
            else:
                self.input_field.setCheckState(Qt.Unchecked)
        elif self.input_type == InputTypes.ENUM:
            if self.input_field.count() == 0:
                return
            index = self.input_field.findData(value)
            self.input_field.setCurrentIndex(index)
        else:
            self.input_field.setText(str(value))

        if reset_change_state:
            self.changed = False

    def disable(self, tooltip: str = None):
        """
        Disable the input field and gray out the label

        Parameters
        ----------
        tooltip: str, optional
            A tooltip to be displayed on label and input field. Default is None
        """
        self.input_field.setEnabled(False)
        self.label.setStyleSheet("color: gray")
        self.set_tooltip(tooltip)
        if self.input_type == InputTypes.BOOLEAN:
            self.input_field.setChecked(False)

    def set_tooltip(self, tooltip: str):
        """
        Display a tooltip on label and input field

        Parameters
        ----------
        tooltip: str
            The tooltip string
        """
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
        """
        Enable the input field and remove gray out from the label
        """
        self.input_field.setEnabled(True)
        self.set_tooltip(self.tooltip)
        self.label.setStyleSheet("")

    def get_value(self) -> str:
        """
        Return
        ----------
        The value of the input field as a string
        """
        if self.input_type == InputTypes.ENUM:
            value = self.input_field.itemData(self.input_field.currentIndex()).name
        elif self.input_type == InputTypes.BOOLEAN:
            if self.input_field.checkState() == Qt.Checked:
                value = 'true'
            else:
                value = "false"
        else:
            value = self.input_field.text()

        return value

    def get_typed_value(self):
        """
        Return
        ----------
        The value of the input field as a boolean, Enum or string
        """
        if self.input_type == InputTypes.ENUM:
            value = self.input_field.itemData(self.input_field.currentIndex())
        elif self.input_type == InputTypes.BOOLEAN:
            return self.input_field.checkState() == Qt.Checked
        else:
            value = self.input_field.text()

        return value


