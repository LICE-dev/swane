"""Head-less test for :class:`swane.ui.ToolReferenceWindow`."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from PySide6.QtWidgets import QDialog

from swane.ui.ToolReferenceWindow import ToolReferenceWindow
from swane.utils.ToolReference import Package


def test_tool_reference_window_builds(qtbot):
    window = ToolReferenceWindow(default_tab=Package.FSL, search_string="bet")
    qtbot.addWidget(window)
    assert isinstance(window, QDialog)
    assert window.windowTitle() != ""
