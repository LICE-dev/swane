"""Head-less tests for :class:`swane.ui.SubjectTab.SubjectTab`."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane import strings
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
