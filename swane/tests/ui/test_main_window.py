"""Head-less construction tests for the top-level SWANe GUI.

The real application spins up an update-check thread (network) on start; the
``offline_update`` / ``main_window`` fixtures (ui/conftest.py) keep it offline.
"""

from PySide6.QtWidgets import QDialog, QTabWidget

from swane.ui.PreferencesWindow import PreferencesWindow


def test_main_window_builds(main_window):
    assert main_window.dependency_manager is not None
    # the central tabbed area is present
    assert isinstance(main_window.main_tab, QTabWidget)
    assert main_window.main_tab.count() >= 1


class TestPreferencesWindow:

    def test_global_preferences_dialog(self, qtbot, global_config, dependency_manager):
        dialog = PreferencesWindow(global_config, dependency_manager, is_workflow=False)
        qtbot.addWidget(dialog)
        assert isinstance(dialog, QDialog)
        assert dialog.windowTitle() != ""

    def test_workflow_preferences_dialog(self, qtbot, global_config, dependency_manager):
        dialog = PreferencesWindow(global_config, dependency_manager, is_workflow=True)
        qtbot.addWidget(dialog)
        assert isinstance(dialog, QDialog)
        assert dialog.windowTitle() != ""
