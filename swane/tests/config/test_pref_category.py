"""Unit tests for :class:`PrefCategory` and :class:`PreferenceEntry`."""

from swane.config.PrefCategory import PrefCategory
from swane.config.PreferenceEntry import PreferenceEntry
from swane.config.config_enums import InputTypes


def test_pref_category_fields():
    category = PrefCategory("performance", "Performance")
    assert category.name == "performance"
    assert category.label == "Performance"


def test_preference_entry_accepts_valid_kwargs():
    entry = PreferenceEntry(
        input_type=InputTypes.INT, label="Cores", tooltip="hint", restart=True
    )
    assert entry.input_type == InputTypes.INT
    assert entry.label == "Cores"
    assert entry.tooltip == "hint"
    assert entry.restart is True


def test_preference_entry_rejects_wrong_types():
    # check_type refuses a non-str label, so the class default is kept
    entry = PreferenceEntry(label=123)
    assert entry.label == ""
    # unknown keys are ignored entirely
    entry2 = PreferenceEntry(not_a_field="x")
    assert not hasattr(entry2, "not_a_field")
