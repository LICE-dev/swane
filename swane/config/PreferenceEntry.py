from swane.config.config_enums import InputTypes


class PreferenceEntry:
    input_type = InputTypes.TEXT
    label = ""
    default = None
    tooltip = ""
    range = None
    dependency = None
    dependency_fail_tooltip = None
    pref_requirement = None
    pref_requirement_fail_tooltip = None
    input_requirement = None
    input_requirement_fail_tooltip = None
    restart = False
    validate_on_change = False
    informative_text = None
    box_text = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key) and PreferenceEntry.check_type(key, value):
                setattr(self, key, value)

    @staticmethod
    def check_type(key, value):
        types = {
                'input_type': InputTypes,
                "label": str,
                "tooltip": str,
                "range": list,
                "dependency": str,
                "dependency_fail_tooltip": str,
                "pref_requirement": dict,
                "pref_requirement_fail_tooltip": str,
                "input_requirement": list,
                "input_requirement_fail_tooltip": str,
                "restart": bool,
                "validate_on_change": bool,
                "informative_text": list,
                "box_text": str,

        }
        if key in types:
            return type(value) is types[key]
        return True



