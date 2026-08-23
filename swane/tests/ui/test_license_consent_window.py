"""Head-less test for :class:`swane.ui.LicenseConsentWindow`.

These tests need a real Qt binding; when PySide6 is unavailable or broken they
skip at module load so the suite stays runnable everywhere.
"""

import pytest
from swane.utils.qt_compat import QT_AVAILABLE

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="requires a working Qt binding")

if QT_AVAILABLE:
    from PySide6.QtWidgets import QDialog, QLabel
    from swane.ui.LicenseConsentWindow import LicenseConsentWindow
    from swane.utils.license_consent import ResolvedLicense, LicenseSource
    from swane import strings


def _mk(text="line\n" * 500):
    return [
        ResolvedLicense("fsl", "FSL", text, False, LicenseSource.INSTALLED),
        ResolvedLicense("freesurfer", "FreeSurfer", text, False, LicenseSource.ONLINE),
    ]


def test_accept_disabled_until_scrolled(qtbot):
    win = LicenseConsentWindow(_mk())
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    assert not win._accept_btn.isEnabled()
    browser = win._current_browser()
    browser.verticalScrollBar().setValue(browser.verticalScrollBar().maximum())
    assert win._accept_btn.isEnabled()


def test_sequence_and_atomic_accept(qtbot):
    win = LicenseConsentWindow(_mk())
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    # Page 1
    b = win._current_browser()
    b.verticalScrollBar().setValue(b.verticalScrollBar().maximum())
    win._accept_btn.click()
    # Page 2
    b = win._current_browser()
    b.verticalScrollBar().setValue(b.verticalScrollBar().maximum())
    win._accept_btn.click()
    assert win.result() == QDialog.Accepted
    assert win.accepted_tool_ids == ["fsl", "freesurfer"]


def test_short_license_enables_immediately(qtbot):
    win = LicenseConsentWindow([
        ResolvedLicense("fsl", "FSL", "short", False, LicenseSource.INSTALLED),
    ])
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    assert win._accept_btn.isEnabled()


def test_long_html_license_starts_disabled(qtbot):
    # A long HTML license (comparable to the ~95 KB FSL HTML page): the button
    # must NOT unlock prematurely just because the document layout has not been
    # computed at the first showEvent (scrollbar maximum still 0). It must start
    # disabled and require scrolling to the end.
    html = "<html><body>" + ("<p>License paragraph.</p>\n" * 5000) + "</body></html>"
    win = LicenseConsentWindow([
        ResolvedLicense("fsl", "FSL", html, True, LicenseSource.ONLINE),
    ])
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    assert not win._accept_btn.isEnabled()
    browser = win._current_browser()
    browser.verticalScrollBar().setValue(browser.verticalScrollBar().maximum())
    assert win._accept_btn.isEnabled()


def test_license_browser_is_monospace_panel(qtbot):
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QFrame

    res = [ResolvedLicense("fsl", "FSL", "text", False, LicenseSource.INSTALLED)]
    win = LicenseConsentWindow(res)
    qtbot.addWidget(win)
    browser = win._current_browser()
    mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    assert browser.font().family() == mono.family()
    assert browser.frameShape() == QFrame.StyledPanel
    # The progress title must stay more prominent than the license text
    assert win._progress.font().bold()
    assert win._progress.font().pointSizeF() > browser.font().pointSizeF()


def _label_texts(win):
    return [w.text() for w in win.findChildren(QLabel)]


def test_online_warning_shown_by_default(qtbot):
    res = [ResolvedLicense("slicer", "3D Slicer", "x", False, LicenseSource.ONLINE)]
    win = LicenseConsentWindow(res)
    qtbot.addWidget(win)
    expected = strings.license_consent_source_online.format(tool="3D Slicer")
    assert any(expected in t for t in _label_texts(win))


def test_online_warning_suppressed_when_official(qtbot):
    # Slicer: online is the official source -> no "installed not found" warning
    res = [
        ResolvedLicense(
            "slicer", "3D Slicer", "x", False, LicenseSource.ONLINE,
            show_source_warning=False,
        )
    ]
    win = LicenseConsentWindow(res)
    qtbot.addWidget(win)
    expected = strings.license_consent_source_online.format(tool="3D Slicer")
    assert all(expected not in t for t in _label_texts(win))


def test_gate_returns_true_when_nothing_to_consent(qtbot, monkeypatch, global_config, offline_update):
    import swane.ui.MainWindow as mw
    from swane.ui.MainWindow import MainWindow
    monkeypatch.setattr(mw, "tools_needing_consent", lambda dm, cfg: [])
    window = MainWindow(global_config)
    qtbot.addWidget(window)
    assert window.run_license_consent_gate() is True
