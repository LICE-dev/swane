"""Head-less construction test for :class:`swane.ui.SubjectTab.SubjectTab`."""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane.ui.SubjectTab import SubjectTab
from swane.utils.Subject import Subject, SubjectRet


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
