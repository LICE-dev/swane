"""Blocking, sequential dialog to accept external tool licenses at startup."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontDatabase, QPalette
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

        # Base point size for the license text; the progress title is made
        # deliberately larger/bold so it stays more prominent than the license.
        base_pt = self.font().pointSizeF()
        if base_pt <= 0:
            base_pt = 10.0
        self._license_point_size = base_pt

        self._progress = QLabel("")
        title_font = self._progress.font()
        title_font.setBold(True)
        title_font.setPointSizeF(base_pt + 2)
        self._progress.setFont(title_font)
        root.addWidget(self._progress)

        self._stack = QStackedWidget()
        self._browsers = []
        for res in self._licenses:
            page = QWidget()
            lay = QVBoxLayout()

            if res.show_source_warning and res.source is LicenseSource.ONLINE:
                warn = QLabel(
                    strings.license_consent_source_online.format(tool=res.display_name)
                )
                warn.setWordWrap(True)
                warn.setStyleSheet("color: #b06000;")
                lay.addWidget(warn)
            elif res.show_source_warning and res.source is LicenseSource.BUNDLED:
                warn = QLabel(
                    strings.license_consent_source_bundled.format(tool=res.display_name)
                )
                warn.setWordWrap(True)
                warn.setStyleSheet("color: #b06000;")
                lay.addWidget(warn)

            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            self._style_license_browser(browser)
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

    def _style_license_browser(self, browser):
        """
        Give the license view a monospace, inset "code panel" look.

        The panel background is the active palette Base nudged toward the Text
        (foreground) color: this darkens it in light themes and lightens it in
        dark themes, so it reads as a clearly distinct "grayer" panel while
        keeping the text readable, harmonizing with the system theme both ways.
        The license font is a touch smaller than the (bold) progress title so
        the title stays the more prominent element.
        """
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSizeF(self._license_point_size)
        browser.setFont(mono)
        browser.setFrameShape(QFrame.StyledPanel)
        browser.setFrameShadow(QFrame.Sunken)

        palette = browser.palette()
        base = palette.color(QPalette.Base)
        text = palette.color(QPalette.Text)
        # 90% Base + 10% Text: a subtle shift toward the theme's foreground (a
        # light gray on light themes, a slightly lighter panel on dark ones),
        # visible but gentle and readable.
        panel = QColor(
            round(base.red() * 0.90 + text.red() * 0.10),
            round(base.green() * 0.90 + text.green() * 0.10),
            round(base.blue() * 0.90 + text.blue() * 0.10),
        )
        palette.setColor(QPalette.Base, panel)
        browser.setPalette(palette)

    def _current_browser(self):
        return self._browsers[self._stack.currentIndex()]

    def _sync_page(self):
        idx = self._stack.currentIndex()
        self._progress.setText(
            strings.license_consent_progress.format(
                current=idx + 1,
                total=len(self._licenses),
                tool=self._licenses[idx].display_name,
            )
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
