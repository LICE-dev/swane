"""Head-less tests for PreferenceUIEntry.disable_combo_option's fallback."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList
from swane.config.preference_list import GLOBAL_PREFERENCES
from swane.ui.PreferenceUIEntry import PreferenceUIEntry

SYNTH = GlobalPrefCategoryList.SYNTH


@pytest.fixture
def deskull_combo(qtbot, global_config):
    """The deskull engine combo with ANTSPYNET (its first option) selected."""
    global_config[SYNTH]["deskull_engine"] = DeskullEngine.ANTSPYNET.name
    entry = PreferenceUIEntry(
        SYNTH,
        "deskull_engine",
        global_config,
        GLOBAL_PREFERENCES[SYNTH]["deskull_engine"],
    )
    qtbot.addWidget(entry.input_field)
    assert entry.input_field.currentData() == DeskullEngine.ANTSPYNET
    return entry


def test_disabling_selected_option_moves_to_default(deskull_combo):
    deskull_combo.default = DeskullEngine.BET

    deskull_combo.disable_combo_option(DeskullEngine.ANTSPYNET, False, "no RAM")

    assert deskull_combo.input_field.currentData() == DeskullEngine.BET
    assert deskull_combo.changed is True


def test_disabled_default_moves_to_first_enabled_option(deskull_combo):
    # Regression: the fallback was always index 0, i.e. the disabled
    # ANTSPYNET itself, which then stayed selected and was saved.
    deskull_combo.default = DeskullEngine.ANTSPYNET

    deskull_combo.disable_combo_option(DeskullEngine.ANTSPYNET, False, "no RAM")

    assert deskull_combo.input_field.currentData() == DeskullEngine.SYNTHSTRIP


def test_all_options_disabled_leaves_selection(deskull_combo):
    for member in (DeskullEngine.BET, DeskullEngine.SYNTHSTRIP):
        deskull_combo.disable_combo_option(member, False, "unavailable")

    deskull_combo.disable_combo_option(DeskullEngine.ANTSPYNET, False, "no RAM")

    assert deskull_combo.input_field.currentData() == DeskullEngine.ANTSPYNET
