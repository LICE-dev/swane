"""Head-less tests for :class:`swane.ui.PreferenceWizardWindow`."""

from swane.ui.PreferenceWizardWindow import PreferenceWizardWindow, UserPreferences


class TestPreferenceWizard:

    def test_build(self, qtbot, global_config, dependency_manager):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        assert wizard.windowTitle() != ""
        assert isinstance(wizard.user_prefs, UserPreferences)
        assert wizard._stack.count() >= 1

    def test_navigation_next_then_back(self, qtbot, global_config, dependency_manager):
        wizard = PreferenceWizardWindow(global_config, dependency_manager)
        qtbot.addWidget(wizard)
        start = wizard._stack.currentIndex()
        wizard._go_next()
        assert wizard._stack.currentIndex() >= start
        wizard._go_back()
        assert wizard._stack.currentIndex() == start
