"""Head-less test for :class:`swane.ui.ToolReferenceWindow`."""

from PySide6.QtWidgets import QDialog

from swane.ui.ToolReferenceWindow import ToolReferenceWindow
from swane.utils.ToolReference import Package


def test_tool_reference_window_builds(qtbot):
    window = ToolReferenceWindow(default_tab=Package.FSL, search_string="bet")
    qtbot.addWidget(window)
    assert isinstance(window, QDialog)
    assert window.windowTitle() != ""
