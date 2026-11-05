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
    from swane.config import dependency_policy

    monkeypatch.setattr(main_window_module, "is_windows", lambda: True)
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
    window = request.getfixturevalue("main_window")
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in window.homeTab.findChildren(QLabel)]
    assert any("experimental" in t for t in texts)


def test_home_tab_hides_windows_notice_when_fsl_mandatory(monkeypatch, request):
    import swane.ui.MainWindow as main_window_module
    from swane.config import dependency_policy

    monkeypatch.setattr(main_window_module, "is_windows", lambda: True)
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
    window = request.getfixturevalue("main_window")
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in window.homeTab.findChildren(QLabel)]
    assert not any("experimental" in t for t in texts)


def test_update_available_shows_conda_installer_command(monkeypatch, main_window):
    from PySide6.QtWidgets import QMessageBox

    captured = {}

    def fake_exec(self):
        captured["text"] = self.text()
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    main_window.update_available("1.2.3")

    assert "1.2.3" in captured["text"]
    assert (
        "curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash"
        in captured["text"]
    )
    assert "pip3 install --upgrade swane" not in captured["text"]


def test_about_changelog_link_points_to_wiki_12_changelog():
    from swane.resources import strings

    assert strings.aboutwindow_wiki_changelog == (
        "Link to versions <a href='https://github.com/LICE-dev/swane/wiki/12-Changelog'>changelog</a>"
    )


def test_saving_preferences_revalidates_ram_requirements(monkeypatch, main_window):
    """A lower ram_gb saved from the Global Preferences must not leave an
    engine selected whose RAM requirement no longer fits (S3.2): its node
    would exceed the workflow budget and every workflow would be refused.
    """
    import swane.ui.MainWindow as main_window_module
    from swane.config.config_enums import DeskullEngine, GlobalPrefCategoryList

    config = main_window.global_config
    synth = GlobalPrefCategoryList.SYNTH
    config[synth]["deskull_engine"] = DeskullEngine.ANTSPYNET.name

    class _SavedLowRam:
        """Stands in for the dialog: saves a ram_gb below ANTSPYNET's 5 GB."""

        def __init__(self, global_config, *args):
            self.global_config = global_config

        def exec(self):
            self.global_config[GlobalPrefCategoryList.PERFORMANCE]["ram_gb"] = "2.5"
            self.global_config.save()
            return 1

    # BET (no RAM requirement) is the engine left that fits on any host.
    monkeypatch.setattr(main_window.dependency_manager, "is_fsl", lambda: True)
    monkeypatch.setattr(main_window, "check_running_workflows", lambda: False)
    monkeypatch.setattr(main_window_module, "PreferencesWindow", _SavedLowRam)

    main_window.edit_config()

    assert config.getenum_safe(synth, "deskull_engine") != DeskullEngine.ANTSPYNET


class TestPreferenceWizardFromMainWindow:
    """Rerunning the wizard (Menu -> Configuration Wizard) must leave no
    generated workflow or open subject configuration built on the previous
    resources."""

    @staticmethod
    def _open_subject_tab(main_window, tmp_path):
        from types import SimpleNamespace

        from swane.config.ConfigManager import ConfigManager

        folder = tmp_path / "subject"
        folder.mkdir()
        tab = SimpleNamespace(
            subject=SimpleNamespace(
                config=ConfigManager(
                    subject_folder=str(folder),
                    global_config=main_window.global_config,
                )
            ),
            resets=[],
        )
        tab.reset_workflow = lambda: tab.resets.append(True)
        main_window.subject_tab_array = [tab]
        return tab

    def test_opening_the_wizard_resets_the_workflows(
        self, monkeypatch, tmp_path, main_window
    ):
        import swane.ui.MainWindow as main_window_module

        tab = self._open_subject_tab(main_window, tmp_path)
        resets_at_exec = []

        class _Wizard:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                # Cancelled: the workflows are reset all the same
                resets_at_exec.append(len(tab.resets))
                return 0

        monkeypatch.setattr(main_window, "check_running_workflows", lambda: False)
        monkeypatch.setattr(main_window_module, "PreferenceWizardWindow", _Wizard)

        main_window.start_preference_wizard()

        assert resets_at_exec == [1]

    def test_a_lower_ram_revalidates_the_open_subjects(
        self, monkeypatch, tmp_path, main_window
    ):
        import swane.ui.MainWindow as main_window_module
        from swane.config.config_enums import FreesurferStep, GlobalPrefCategoryList
        from swane.utils.DataInputList import DataInputList
        from swane.utils.ResourceManager import ResourceManager

        perf = GlobalPrefCategoryList.PERFORMANCE
        dependency_manager = main_window.dependency_manager
        monkeypatch.setattr(dependency_manager, "is_freesurfer", lambda: True)
        monkeypatch.setattr(dependency_manager, "is_freesurfer_synth", lambda: True)
        main_window.global_config[perf]["ram_gb"] = str(
            ResourceManager.synth_seg_ram_requirements()
        )
        tab = self._open_subject_tab(main_window, tmp_path)
        subject_config = tab.subject.config
        subject_config[DataInputList.T13D][
            "freesurfer_step"
        ] = FreesurferStep.SYNTHSEG.name

        class _LowRamWizard:
            """Stands in for the wizard: applies a profile below SynthSeg's RAM."""

            def __init__(self, global_config, *args, **kwargs):
                self.global_config = global_config

            def exec(self):
                self.global_config[perf]["ram_gb"] = "8.0"
                self.global_config.save()
                return 1

        monkeypatch.setattr(main_window, "check_running_workflows", lambda: False)
        monkeypatch.setattr(main_window_module, "PreferenceWizardWindow", _LowRamWizard)

        main_window.start_preference_wizard()

        assert (
            subject_config.getenum_safe(DataInputList.T13D, "freesurfer_step")
            is not FreesurferStep.SYNTHSEG
        )


class TestAlreadyLoadedSubjectGuard:
    """``search_subject_dir`` refuses a subject folder already open in a tab,
    however the path is spelled (``Subject.folder`` is normalised, the
    QFileDialog path uses ``/`` even on Windows)."""

    @pytest.fixture
    def guard(self, monkeypatch, main_window, tmp_path):
        import types

        from swane.ui import MainWindow as main_window_module
        from swane.utils.Subject import Subject, SubjectRet

        folder = tmp_path / "subj_1"
        folder.mkdir()
        open_tab = types.SimpleNamespace(
            subject=types.SimpleNamespace(
                folder=os.path.abspath(str(folder)),
                is_workflow_process_alive=lambda: False,
            )
        )
        main_window.subject_tab_array.append(open_tab)
        monkeypatch.setattr(main_window, "check_subject_limit", lambda: True)
        calls = {"warnings": 0, "loads": []}

        def fake_exec(box):
            calls["warnings"] += 1

        def fake_load(subject, path):
            calls["loads"].append(path)
            return SubjectRet.FolderNotFound

        monkeypatch.setattr(main_window_module.QMessageBox, "exec", fake_exec)
        monkeypatch.setattr(Subject, "load", fake_load)
        yield main_window, folder, calls
        main_window.subject_tab_array.remove(open_tab)

    def _assert_refused(self, calls):
        assert calls == {"warnings": 1, "loads": []}

    def test_forward_slash_path(self, guard):
        window, folder, calls = guard
        window.search_subject_dir(folder_path=str(folder).replace(os.sep, "/"))
        self._assert_refused(calls)

    def test_trailing_separator(self, guard):
        window, folder, calls = guard
        window.search_subject_dir(folder_path=str(folder) + os.sep)
        self._assert_refused(calls)

    def test_symlinked_folder(self, guard, tmp_path):
        window, folder, calls = guard
        link = tmp_path / "link"
        try:
            link.symlink_to(folder, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks not available")
        window.search_subject_dir(folder_path=str(link))
        self._assert_refused(calls)

    def test_other_folder_is_loaded(self, guard, tmp_path):
        window, folder, calls = guard
        other = str(tmp_path / "subj_2")
        window.search_subject_dir(folder_path=other)
        assert calls == {"warnings": 0, "loads": [other]}

    def test_cancelled_dialog_is_not_a_duplicate(self, guard, monkeypatch):
        """An empty path (dialog cancelled) must not match the subject folder
        even when it is the current directory."""
        window, folder, calls = guard
        monkeypatch.chdir(folder)
        window.search_subject_dir(folder_path="")
        assert calls == {"warnings": 0, "loads": [""]}
