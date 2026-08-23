"""Head-less construction tests for the top-level SWANe GUI.

The real application spins up an update-check thread (network) on start; the
``offline_update`` / ``main_window`` fixtures (ui/conftest.py) keep it offline.
"""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from PySide6.QtWidgets import QDialog, QTabWidget

from swane.ui.PreferencesWindow import PreferencesWindow


def test_main_window_builds(main_window):
    assert main_window.dependency_manager is not None
    # the central tabbed area is present
    assert isinstance(main_window.main_tab, QTabWidget)
    assert main_window.main_tab.count() >= 1


def test_home_entry_renders_label_with_link(main_window):
    # add_home_entry renders whatever HTML the dependency label carries
    # (dependency labels already embed the license link via version_with_license)
    from swane.utils.DependencyManager import Dependence, DependenceStatus

    row = 50
    main_window.add_home_entry(
        Dependence(DependenceStatus.DETECTED, 'FSL detected (6.0.6 - <a href="x">license</a>)'),
        row,
    )
    label = main_window.home_grid_layout.itemAtPosition(row, 1).widget()
    assert "<a href" in label.text()


class TestPreferencesWindow:

    def test_global_preferences_dialog(self, qtbot, global_config, dependency_manager):
        dialog = PreferencesWindow(global_config, dependency_manager, is_workflow=False)
        qtbot.addWidget(dialog)
        assert isinstance(dialog, QDialog)
        assert dialog.windowTitle() != ""

    def test_workflow_preferences_dialog(
        self, qtbot, global_config, dependency_manager
    ):
        dialog = PreferencesWindow(global_config, dependency_manager, is_workflow=True)
        qtbot.addWidget(dialog)
        assert isinstance(dialog, QDialog)
        assert dialog.windowTitle() != ""
