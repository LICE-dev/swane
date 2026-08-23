"""Blocking, sequential dialog to accept external tool licenses at startup."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QWidget,
    QLabel,
    QPushButton,
    QTextBrowser,
    QFrame,
)

from swane import strings
from swane.utils.license_consent import LicenseSource


class LicenseConsentWindow(QDialog):
    def __init__(self, resolved_licenses, parent=None):
        super().__init__(parent)
        self._licenses = list(resolved_licenses)
        self.accepted_tool_ids = []

        self.setWindowTitle(strings.license_consent_title)
        self.setModal(True)
        self.resize(720, 640)

        root = QVBoxLayout()

        banner = QLabel(strings.license_consent_banner)
        banner.setWordWrap(True)
        banner.setStyleSheet("font-weight: 600;")
        root.addWidget(banner)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        self._progress = QLabel("")
        root.addWidget(self._progress)

        self._stack = QStackedWidget()
        self._browsers = []
        for res in self._licenses:
            page = QWidget()
            lay = QVBoxLayout()

            if res.source is LicenseSource.ONLINE:
                warn = QLabel(strings.license_consent_source_online.format(tool=res.display_name))
                warn.setWordWrap(True)
                warn.setStyleSheet("color: #b06000;")
                lay.addWidget(warn)
            elif res.source is LicenseSource.BUNDLED:
                warn = QLabel(strings.license_consent_source_bundled.format(tool=res.display_name))
                warn.setWordWrap(True)
                warn.setStyleSheet("color: #b06000;")
                lay.addWidget(warn)

            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            if res.is_html:
                browser.setHtml(res.text)
            else:
                browser.setPlainText(res.text)
            browser.verticalScrollBar().valueChanged.connect(self._maybe_enable_accept)
            # A long document's layout may not be computed yet at the first
            # showEvent, leaving the scrollbar maximum at 0 (which otherwise
            # reads as "fits without scrolling"). Re-evaluate whenever the
            # document's laid-out size changes so a long license cannot unlock
            # the accept button prematurely.
            browser.document().documentLayout().documentSizeChanged.connect(
                self._maybe_enable_accept
            )
            lay.addWidget(browser)
            self._browsers.append(browser)

            page.setLayout(lay)
            self._stack.addWidget(page)

        root.addWidget(self._stack)

        hint = QLabel(strings.license_consent_scroll_hint)
        hint.setStyleSheet("color: #666;")
        root.addWidget(hint)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self._accept_btn = QPushButton(strings.license_consent_accept_button)
        self._accept_btn.clicked.connect(self._accept_current)
        nav.addWidget(self._accept_btn)
        root.addLayout(nav)

        self.setLayout(root)
        self._sync_page()

    def _current_browser(self):
        return self._browsers[self._stack.currentIndex()]

    def _sync_page(self):
        idx = self._stack.currentIndex()
        self._progress.setText(
            strings.license_consent_progress.format(current=idx + 1, total=len(self._licenses))
        )
        self._maybe_enable_accept()

    def _maybe_enable_accept(self, *args):
        bar = self._current_browser().verticalScrollBar()
        at_bottom = bar.maximum() == 0 or bar.value() >= bar.maximum()
        self._accept_btn.setEnabled(at_bottom)

    def _accept_current(self):
        idx = self._stack.currentIndex()
        if idx < len(self._licenses) - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._sync_page()
            return
        # Last page: atomic accept
        self.accepted_tool_ids = [res.tool_id for res in self._licenses]
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        # Defer the initial check to the next event-loop iteration. At the first
        # showEvent a long document's layout may not be computed yet, so the
        # scrollbar maximum can still be 0 and be misread as "fits without
        # scrolling". Postponing lets Qt finish the layout first, so only a
        # license genuinely shorter than the viewport enables immediately.
        QTimer.singleShot(0, self._maybe_enable_accept)
