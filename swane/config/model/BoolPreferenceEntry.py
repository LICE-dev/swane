from swane.config.model.PreferenceEntry import PreferenceEntry

class BoolPreferenceEntry(PreferenceEntry):
    
    def __init__(self, **kwargs):
        self.types["default"] = bool
        
        super.__init__(BoolPreferenceEntry, self, **kwargs)
                
    def set_value(self, value: bool):
        if type(value) is bool:
            self.value = value
        else:
            self.value = self.default