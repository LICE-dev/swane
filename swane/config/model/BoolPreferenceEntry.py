from swane.config.model.PreferenceEntry import PreferenceEntry
from configparser import ConfigParser


class BoolPreferenceEntry(PreferenceEntry):
    
    def __init__(self, **kwargs):
        self.types["default"] = bool
        super().__init__(**kwargs)

    @PreferenceEntry.value.setter
    def value(self, value: bool):
        if type(value) is bool:
            self._value = value
        else:
            self._value = self.default

    def str_2_value(self, value: str):
        value = value.lower()
        if value in ConfigParser.BOOLEAN_STATES:
            self.value = ConfigParser.BOOLEAN_STATES[value]
        else:
            self.value = self.default
