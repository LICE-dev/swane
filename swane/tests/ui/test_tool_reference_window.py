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


def test_tool_reference_window_has_ants_tab(qtbot):
    window = ToolReferenceWindow(default_tab=Package.ANTS)
    qtbot.addWidget(window)
    assert Package.ANTS in window._package_ui
    labels = [window._tab_widget.tabText(i) for i in range(window._tab_widget.count())]
    assert "ANTS" in labels


def test_tool_reference_window_has_nilearn_tab(qtbot):
    window = ToolReferenceWindow(default_tab=Package.NILEARN)
    qtbot.addWidget(window)
    assert Package.NILEARN in window._package_ui
    labels = [window._tab_widget.tabText(i) for i in range(window._tab_widget.count())]
    assert "NILEARN" in labels


def test_tool_reference_window_dimensions(qtbot):
    # Opened with a specific search string as when clicking a workflow node
    window_filtered = ToolReferenceWindow(default_tab=Package.FSL, search_string="bet")
    qtbot.addWidget(window_filtered)
    window_filtered.show()

    assert window_filtered.minimumWidth() >= ToolReferenceWindow.MIN_WIDTH
    assert window_filtered.minimumHeight() >= ToolReferenceWindow.MIN_HEIGHT
    assert window_filtered.width() == ToolReferenceWindow.DEFAULT_WIDTH
    assert window_filtered.height() == ToolReferenceWindow.DEFAULT_HEIGHT

    # Opened without filter (e.g. from menu)
    window_unfiltered = ToolReferenceWindow()
    qtbot.addWidget(window_unfiltered)
    window_unfiltered.show()

    assert window_unfiltered.minimumWidth() >= ToolReferenceWindow.MIN_WIDTH
    assert window_unfiltered.minimumHeight() >= ToolReferenceWindow.MIN_HEIGHT
    assert window_unfiltered.width() == ToolReferenceWindow.DEFAULT_WIDTH
    assert window_unfiltered.height() == ToolReferenceWindow.DEFAULT_HEIGHT
