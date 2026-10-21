"""Head-less tests for :class:`swane.ui.SubjectTab.SubjectTab`."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane.resources import strings
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals
from swane.ui.SubjectTab import SubjectTab
from swane.utils.DependencyManager import DependencyManager
from swane.utils.Subject import Subject, SubjectRet
from swane.workers.SlicerExportWorker import SlicerExportWorker


def _loaded_subject(global_config, dependency_manager, name="subj_ui"):
    subject = Subject(global_config, dependency_manager)
    assert subject.create_new_subject_dir(name) == SubjectRet.ValidFolder
    return subject


class TestSubjectTab:

    def test_build_and_initial_tab_states(self, qtbot, main_window):
        subject = _loaded_subject(
            main_window.global_config, main_window.dependency_manager
        )
        tab = SubjectTab(main_window.global_config, subject, main_window)
        qtbot.addWidget(tab)

        assert tab.count() == 3
        assert tab.subject is subject
        # exec/result tabs start disabled until data is loaded and a workflow runs
        assert tab.isTabEnabled(SubjectTab.DATATAB) is True
        assert tab.isTabEnabled(SubjectTab.EXECTAB) is False
        assert tab.isTabEnabled(SubjectTab.RESULTTAB) is False

    def test_workflow_lifecycle_updates_tab_states(
        self, qtbot, monkeypatch, main_window, tmp_path
    ):
        """Generate -> execute -> generate scene, with a mocked ``Subject``.

        Mirrors what the retired heavy ``test_complete_workflow.py`` smoke test
        checked end to end against a real FSL/FreeSurfer/Slicer toolchain and a
        hand-prepared subject folder: here the same ``SubjectTab`` wiring (button
        enabling, tab enabling, the async execution-report callback) is exercised
        against a mocked ``Subject``, so it runs anywhere without real tools.
        """
        subject = _loaded_subject(
            main_window.global_config,
            main_window.dependency_manager,
            name="subj_lifecycle",
        )
        tab = SubjectTab(main_window.global_config, subject, main_window)
        qtbot.addWidget(tab)

        # --- Generate workflow: exec button enables, generate button disables.
        class FakeWorkflow:
            @staticmethod
            def get_node_array():
                return {}

        subject.workflow = FakeWorkflow()
        monkeypatch.setattr(
            subject, "generate_workflow", lambda *a, **k: SubjectRet.GenWfCompleted
        )

        # QTabWidget.setTabEnabled(index, False) disables the page widget
        # itself, so exec_button.isEnabled() (ancestor-aware) would read False
        # regardless of exec_button_set_enabled() below unless EXECTAB is
        # enabled first -- normally done by data loading, out of scope here.
        tab.setTabEnabled(SubjectTab.EXECTAB, True)

        # Mock preload methods to avoid network requests and subprocesses in tests
        from swane.workers.WorkflowGenerateWorker import WorkflowGenerateWorker

        monkeypatch.setattr(
            WorkflowGenerateWorker, "_preload_templates", lambda *args: None
        )
        monkeypatch.setattr(
            WorkflowGenerateWorker, "_preload_models", lambda *args: None
        )

        # Since generate_workflow is now async, we must wait for the finished signal
        # and we can't intercept the worker creation easily, so we just run the
        # worker inline for this test
        monkeypatch.setattr("swane.ui.SubjectTab.start_worker", lambda w: w.run())

        tab.generate_workflow()
        assert tab.exec_button.isEnabled() is True
        assert tab.generate_workflow_button.isEnabled() is False

        # --- Execute: the "started" UI state applies immediately...
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        monkeypatch.setattr(subject, "result_dir", lambda: str(result_dir))
        monkeypatch.setattr(subject, "is_workflow_process_alive", lambda: False)

        captured = {}

        def fake_start_workflow(
            resume=None, resume_freesurfer=None, update_node_callback=None
        ):
            captured["callback"] = update_node_callback
            return SubjectRet.ExecWfStarted

        monkeypatch.setattr(subject, "start_workflow", fake_start_workflow)

        tab.toggle_workflow_execution()
        assert tab.exec_button.text() == strings.EXECBUTTONTEXT_STOP
        assert tab.isTabEnabled(SubjectTab.DATATAB) is False
        assert tab.isTabEnabled(SubjectTab.RESULTTAB) is False

        # --- ...then WORKFLOW_STOP (normally delivered async by
        # WorkflowMonitorWorker) flips the tabs back and enables RESULTTAB, since
        # subject.result_dir() now exists.
        scene_path = tmp_path / "scene.mrml"
        scene_path.write_text("")
        monkeypatch.setattr(subject, "scene_path", lambda: str(scene_path))
        monkeypatch.setattr(
            DependencyManager, "is_slicer", staticmethod(lambda cfg: True)
        )

        captured["callback"](WorkflowReport(WorkflowSignals.WORKFLOW_STOP))
        assert tab.exec_button.text() == strings.subj_tab_wf_executed
        assert tab.isTabEnabled(SubjectTab.DATATAB) is True
        assert tab.isTabEnabled(SubjectTab.RESULTTAB) is True
        assert tab.load_scene_button.isEnabled() is True

        # --- Generate scene: the progress dialog closes once the worker signals
        # completion (mocked here instead of running the real Slicer export).
        monkeypatch.setattr(
            subject,
            "generate_scene",
            lambda callback: callback(SlicerExportWorker.END_MSG),
        )

        progress = tab.generate_scene()
        assert progress.isVisible() is False


def test_workflow_crash_signal_updates_tab_states(
    qtbot, monkeypatch, main_window, tmp_path
):
    subject = _loaded_subject(
        main_window.global_config,
        main_window.dependency_manager,
        name="subj_crash",
    )
    tab = SubjectTab(main_window.global_config, subject, main_window)
    qtbot.addWidget(tab)

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)

    tab.update_node_list(WorkflowReport(WorkflowSignals.WORKFLOW_CRASHED))
    assert tab.workflow_had_error is True


@pytest.mark.parametrize(
    "earlier, expected_texts",
    [
        ([], [strings.subj_tab_wf_crashed]),
        (["node_error"], [strings.subj_tab_wf_node_failed]),
        (["resources"], [strings.subj_tab_wf_insufficient_resources]),
    ],
)
def test_workflow_crash_notice_follows_earlier_reports(
    qtbot, monkeypatch, main_window, earlier, expected_texts
):
    """The workflow process sends WORKFLOW_CRASHED for every failed run: the
    final notice names failed nodes when some were reported, and an
    insufficient resources notice is not followed by a second one."""
    subject = _loaded_subject(
        main_window.global_config,
        main_window.dependency_manager,
        name="subj_crash_notice",
    )
    tab = SubjectTab(main_window.global_config, subject, main_window)
    qtbot.addWidget(tab)

    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()))

    if "node_error" in earlier:
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        node_holder = MagicMock()
        node_holder.isSelected.return_value = False
        tab.node_list = {
            "wf": SimpleNamespace(
                node_list={"node": SimpleNamespace(node_holder=node_holder)},
                node_holder=MagicMock(),
            )
        }
        tab.update_node_list(
            WorkflowReport(WorkflowSignals.NODE_ERROR, long_name="pt.wf.node")
        )
        node_holder.set_art.assert_called_once_with(main_window.ERROR_ICON_FILE)
    if "resources" in earlier:
        tab.update_node_list(
            WorkflowReport(WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES)
        )
    tab.update_node_list(WorkflowReport(WorkflowSignals.WORKFLOW_CRASHED))

    assert shown == expected_texts
    assert tab.workflow_had_error is True


def test_label_from_dicom():
    label_single = SubjectTab.label_from_dicom(176, "Subj01", "MR", "T1_MPRAGE", 1)
    assert label_single == "Subj01 - MR - <b>T1_MPRAGE</b>: 176 images, 1 volume"

    label_multi = SubjectTab.label_from_dicom(320, "Subj01", "MR", "DTI", 32)
    assert label_multi == "Subj01 - MR - <b>DTI</b>: 320 images, 32 volumes"

    # Exception safety
    assert SubjectTab.label_from_dicom(None, None, None, None, None) == ""


def test_label_from_dicom_escapes_dicom_text():
    from PySide6.QtGui import QTextDocument

    label = SubjectTab.label_from_dicom(10, "S<1>", "MR", "T1 <MPR> & 3D", 1)
    assert "<MPR>" not in label
    assert "&lt;MPR&gt; &amp; 3D" in label

    # Rendered text must show the DICOM strings verbatim, with only the bold tag consumed
    doc = QTextDocument()
    doc.setHtml(label)
    assert doc.toPlainText() == "S<1> - MR - T1 <MPR> & 3D: 10 images, 1 volume"

    # An unbalanced tag in the description cannot break the surrounding markup
    doc.setHtml(SubjectTab.label_from_dicom(10, "S", "MR", "<b>x", 1))
    assert doc.toPlainText() == "S - MR - <b>x: 10 images, 1 volume"


def test_label_from_dicom_without_bold():
    label = SubjectTab.label_from_dicom(176, "S", "MR", "T1 & T2", 1, bold=False)
    assert label == "S - MR - T1 &amp; T2: 176 images, 1 volume"


def test_importable_series_list_delegate(qtbot, main_window):
    from swane.ui.HtmlItemDelegate import HtmlItemDelegate

    subject = _loaded_subject(
        main_window.global_config,
        main_window.dependency_manager,
        name="subj_delegate",
    )
    tab = SubjectTab(main_window.global_config, subject, main_window)
    qtbot.addWidget(tab)

    assert isinstance(tab.importable_series_list.itemDelegate(), HtmlItemDelegate)


def test_show_scan_result_populates_importable_series_list(
    qtbot, main_window, tmp_path
):
    from swane.config.config_enums import GlobalPrefCategoryList

    subject = _loaded_subject(
        main_window.global_config,
        main_window.dependency_manager,
        name="subj_scan_result",
    )
    tab = SubjectTab(main_window.global_config, subject, main_window)
    qtbot.addWidget(tab)

    main_window.global_config.set(
        str(GlobalPrefCategoryList.MAIN), "auto_import", "False"
    )

    scan_dir = tmp_path / "dicom_scan"
    scan_dir.mkdir()

    class FakeSeries:
        frames = 176
        modality = "MR"
        description = "T1_MPRAGE"
        volumes = 1
        dicom_locs = ["file1.dcm", "file2.dcm"]
        classification = None

    class FakeSubject:
        subject_name = "Subject01"

    class FakeTree:
        dicom_subjects = {"subj1": FakeSubject()}

        @staticmethod
        def get_subject_list():
            return ["subj1"]

        @staticmethod
        def get_studies_list(s):
            return ["study1"]

        @staticmethod
        def get_series_list(s, st):
            return ["series1"]

        @staticmethod
        def get_series(s, st, se):
            return FakeSeries()

    class FakeWorker:
        dicom_dir = str(scan_dir)
        tree = FakeTree()
        error_message = ""

    tab.show_scan_result(FakeWorker())

    assert len(tab.dicom_scan_series_list) == 1
    assert tab.importable_series_list.count() == 1
    expected_label = "Subject01 - MR - <b>T1_MPRAGE</b>: 176 images, 1 volume"
    assert tab.importable_series_list.item(0).text() == expected_label
    # Tag-free variant used by the auto-import prompt
    assert (
        tab.dicom_scan_series_list[0][5]
        == "Subject01 - MR - T1_MPRAGE: 176 images, 1 volume"
    )

    tab.clear_scan_result()
    assert len(tab.dicom_scan_series_list) == 0
    assert tab.importable_series_list.count() == 0


def test_auto_import_prompt_uses_tag_free_label(
    qtbot, main_window, tmp_path, monkeypatch
):
    from swane.config.config_enums import GlobalPrefCategoryList
    import importlib

    subject_tab_module = importlib.import_module("swane.ui.SubjectTab")
    from PySide6.QtWidgets import QMessageBox

    subject = _loaded_subject(
        main_window.global_config,
        main_window.dependency_manager,
        name="subj_auto_import",
    )
    tab = SubjectTab(main_window.global_config, subject, main_window)
    qtbot.addWidget(tab)

    main_window.global_config.set(
        str(GlobalPrefCategoryList.MAIN), "auto_import", "True"
    )
    data_input = next(iter(subject.input_state_list))
    scan_dir = tmp_path / "dicom_scan"
    scan_dir.mkdir()

    class FakeSeries:
        frames = 10
        modality = "MR"
        description = "T1 <MPR>"
        volumes = 1
        dicom_locs = ["file1.dcm"]
        classification = data_input.value.name

    class FakeSubject:
        subject_name = "Subject01"

    class FakeTree:
        dicom_subjects = {"subj1": FakeSubject()}

        @staticmethod
        def get_subject_list():
            return ["subj1"]

        @staticmethod
        def get_studies_list(s):
            return ["study1"]

        @staticmethod
        def get_series_list(s, st):
            return ["series1"]

        @staticmethod
        def get_series(s, st, se):
            return FakeSeries()

    class FakeWorker:
        dicom_dir = str(scan_dir)
        tree = FakeTree()
        error_message = ""

    texts = []

    class FakeMessageBox:
        Icon = QMessageBox.Icon
        StandardButton = QMessageBox.StandardButton

        def __init__(self, *args, **kwargs):
            pass

        def setText(self, text):
            texts.append(text)

        def exec(self):
            return QMessageBox.StandardButton.No

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    monkeypatch.setattr(subject_tab_module, "QMessageBox", FakeMessageBox)
    tab.show_scan_result(FakeWorker())

    assert len(texts) == 1
    assert "T1 &lt;MPR&gt;" in texts[0]
    assert "<b>T1" not in texts[0]


class _ModalityMismatchHarness:
    """Drives ``SubjectTab.dicom_import_to_folder`` through the modality-mismatch prompt.

    The subject import, the message box and the progress dialog are replaced
    with recorders so the test observes only what the tab does with them.
    """

    def __init__(self, qtbot, main_window, monkeypatch, answer, import_results):
        import importlib
        from PySide6.QtWidgets import QMessageBox

        module = importlib.import_module("swane.ui.SubjectTab")
        subject = _loaded_subject(
            main_window.global_config,
            main_window.dependency_manager,
            name="subj_modality_mismatch",
        )
        self.tab = SubjectTab(main_window.global_config, subject, main_window)
        qtbot.addWidget(self.tab)
        self.data_input = next(iter(subject.input_state_list))

        self.message_texts = []
        self.dialogs = []
        self.import_calls = []
        self.set_error_calls = []
        results = iter(import_results)
        harness = self

        class FakeMessageBox:
            Icon = QMessageBox.Icon
            StandardButton = QMessageBox.StandardButton

            def __init__(self, *args, **kwargs):
                pass

            def setText(self, text):
                harness.message_texts.append(text)

            def exec(self):
                return answer

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        class FakeProgress:
            def __init__(self, *args, **kwargs):
                self.deleted = 0
                harness.dialogs.append(self)

            def deleteLater(self):
                self.deleted += 1

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        def fake_import(**kwargs):
            self.import_calls.append(kwargs)
            return next(results)

        monkeypatch.setattr(module, "QMessageBox", FakeMessageBox)
        monkeypatch.setattr(module, "PersistentProgressDialog", FakeProgress)
        monkeypatch.setattr(subject, "dicom_import_to_folder", fake_import)
        monkeypatch.setattr(subject, "check_input_folder", lambda *a, **k: None)
        monkeypatch.setattr(self.tab, "reset_workflow", lambda: None)
        monkeypatch.setattr(
            self.tab,
            "set_error",
            lambda data_input, tooltip: self.set_error_calls.append(
                (data_input, tooltip)
            ),
        )

    @staticmethod
    def series(name, modality="CT"):
        return ["label", ["%s_1.dcm" % name, "%s_2.dcm" % name], modality, 1]


def test_modality_mismatch_yes_reimports_the_auto_import_series(
    qtbot, main_window, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    harness = _ModalityMismatchHarness(
        qtbot,
        main_window,
        monkeypatch,
        answer=QMessageBox.StandardButton.Yes,
        import_results=[
            SubjectRet.DataImportErrorModality,
            SubjectRet.DataImportCompleted,
        ],
    )
    origin = harness.series("auto")

    # Auto-import: the series is handed in and no row is selected
    assert harness.tab.importable_series_list.currentRow() == -1
    harness.tab.dicom_import_to_folder(harness.data_input, force_copy_list=origin)

    assert strings.subj_tab_selected_series_error not in harness.message_texts
    assert len(harness.import_calls) == 2
    first, second = harness.import_calls
    assert first["force_modality"] is False
    assert second["force_modality"] is True
    assert second["copy_list"] == first["copy_list"] == origin[1]
    assert second["mod"] == first["mod"] == "CT"
    # The outer frame must not clear the state set by the second import or
    # delete the dialog its worker is still updating
    assert harness.set_error_calls == []
    assert [dialog.deleted for dialog in harness.dialogs] == [1, 0]


def test_modality_mismatch_yes_reimports_the_selected_series(
    qtbot, main_window, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    harness = _ModalityMismatchHarness(
        qtbot,
        main_window,
        monkeypatch,
        answer=QMessageBox.StandardButton.Yes,
        import_results=[
            SubjectRet.DataImportErrorModality,
            SubjectRet.DataImportCompleted,
        ],
    )
    harness.tab.dicom_scan_series_list = [
        harness.series("first", "MR"),
        harness.series("second"),
    ]
    harness.tab.importable_series_list.addItem("first")
    harness.tab.importable_series_list.addItem("second")
    harness.tab.importable_series_list.setCurrentRow(1)
    harness.tab.dicom_import_to_folder(harness.data_input)

    assert len(harness.import_calls) == 2
    first, second = harness.import_calls
    assert second["copy_list"] == first["copy_list"] == ["second_1.dcm", "second_2.dcm"]
    assert second["force_modality"] is True
    assert harness.set_error_calls == []
    assert [dialog.deleted for dialog in harness.dialogs] == [1, 0]


def test_modality_mismatch_no_keeps_the_input_in_error(qtbot, main_window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    harness = _ModalityMismatchHarness(
        qtbot,
        main_window,
        monkeypatch,
        answer=QMessageBox.StandardButton.No,
        import_results=[SubjectRet.DataImportErrorModality],
    )
    harness.tab.dicom_import_to_folder(
        harness.data_input, force_copy_list=harness.series("auto")
    )

    assert len(harness.import_calls) == 1
    assert harness.set_error_calls == [(harness.data_input, "")]
    assert len(harness.dialogs) == 1
    assert harness.dialogs[0].deleted >= 1
