"""Head-less test for :class:`swane.ui.LicenseConsentWindow`.

These tests need a real Qt binding; when PySide6 is unavailable or broken they
skip at module load so the suite stays runnable everywhere.
"""

import pytest
from swane.utils.qt_compat import QT_AVAILABLE

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="requires a working Qt binding")

if QT_AVAILABLE:
    from PySide6.QtWidgets import QDialog
    from swane.ui.LicenseConsentWindow import LicenseConsentWindow
    from swane.utils.license_consent import ResolvedLicense, LicenseSource


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
