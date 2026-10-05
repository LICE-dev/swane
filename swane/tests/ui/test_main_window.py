"""Head-less construction tests for the top-level SWANe GUI.

The real application spins up an update-check thread (network) on start; the
``offline_update`` / ``main_window`` fixtures (ui/conftest.py) keep it offline.
"""

import os

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
        Dependence(
            DependenceStatus.DETECTED, 'FSL detected (6.0.6 - <a href="x">license</a>)'
        ),
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


def test_home_tab_shows_windows_notice(monkeypatch, request):
    import swane.ui.MainWindow as main_window_module

    monkeypatch.setattr(main_window_module, "is_windows", lambda: True)
    window = request.getfixturevalue("main_window")
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in window.homeTab.findChildren(QLabel)]
    assert any("experimental" in t for t in texts)


# --- blank spaces in folder names (allowed on Windows only) --------------------


@pytest.fixture
def silent_dialogs(monkeypatch):
    """Record QMessageBox texts instead of showing modal dialogs."""
    import swane.ui.MainWindow as main_window_module

    shown = []

    def fake_exec(box):
        shown.append(box.text())
        return 0

    monkeypatch.setattr(main_window_module.QMessageBox, "exec", fake_exec)
    return shown


def _choose_working_dir(monkeypatch, window, folder):
    import swane.ui.MainWindow as main_window_module

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *args, **kwargs: str(folder)),
    )
    # set_main_working_directory chdirs into the chosen folder: restore cwd.
    monkeypatch.chdir(os.getcwd())
    window.set_main_working_directory()


@pytest.mark.parametrize("windows", [False, True])
def test_working_directory_with_blank_spaces(
    main_window, monkeypatch, tmp_path, silent_dialogs, windows
):
    import swane.utils.platform_and_tools_utils as platform_utils
    from swane.resources import strings

    monkeypatch.setattr(platform_utils, "is_windows", lambda: windows)
    before = main_window.global_config.get_main_working_directory()
    folder = tmp_path / "work space"
    folder.mkdir()

    _choose_working_dir(monkeypatch, main_window, folder)

    if windows:
        assert silent_dialogs == []
        assert main_window.global_config.get_main_working_directory() == str(folder)
    else:
        assert silent_dialogs == [strings.mainwindow_working_dir_space_error]
        assert main_window.global_config.get_main_working_directory() == before


@pytest.mark.parametrize(
    "windows, typed, expected",
    [
        # Linux/macOS: blank spaces become underscores, as always.
        (False, "my subject", "my_subject"),
        # Windows: inner blank spaces are kept; surrounding ones are trimmed
        # (Windows would silently drop the trailing ones from the folder name).
        (True, "  my subject ", "my subject"),
    ],
)
def test_new_subject_name_blank_spaces(
    main_window, monkeypatch, silent_dialogs, windows, typed, expected
):
    import swane.ui.MainWindow as main_window_module
    import swane.utils.platform_and_tools_utils as platform_utils

    monkeypatch.setattr(platform_utils, "is_windows", lambda: windows)
    monkeypatch.setattr(
        main_window_module.QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: (typed, True)),
    )
    opened = []
    monkeypatch.setattr(
        main_window,
        "open_subject_tab",
        lambda subject, **kwargs: opened.append(subject.folder),
    )

    main_window.choose_new_subject_dir()

    main = main_window.global_config.get_main_working_directory()
    assert opened == [os.path.abspath(os.path.join(main, expected))]
    assert os.path.isdir(os.path.join(main, expected))
