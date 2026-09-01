"""Blocking, sequential dialog to accept external tool licenses at startup."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
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
        self._current_index = 0
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

        self._warning = QLabel("")
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet("color: #b06000;")
        root.addWidget(self._warning)

        # Keep one document widget and load only the current license. Creating
        # and laying out every document up front is especially expensive for
        # the large FSL license on low-performance systems.
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._style_license_browser(self._browser)
        self._browser.verticalScrollBar().valueChanged.connect(
            self._maybe_enable_accept
        )
        # A long document's layout may not be computed immediately, leaving the
        # scrollbar maximum at 0. Re-evaluate whenever its laid-out size changes
        # so a long license cannot unlock the accept button prematurely.
        self._browser.document().documentLayout().documentSizeChanged.connect(
            self._maybe_enable_accept
        )
        root.addWidget(self._browser)

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
        return self._browser

    def _sync_page(self):
        idx = self._current_index
        self._progress.setText(
            strings.license_consent_progress.format(
                current=idx + 1,
                total=len(self._licenses),
                tool=self._licenses[idx].display_name,
            )
        )
        self._load_current_license()

    def _load_current_license(self):
        """Load and lay out only the currently displayed license."""
        res = self._licenses[self._current_index]
        warning_text = ""
        if res.show_source_warning and res.source is LicenseSource.ONLINE:
            warning_text = strings.license_consent_source_online.format(
                tool=res.display_name
            )
        elif res.show_source_warning and res.source is LicenseSource.BUNDLED:
            warning_text = strings.license_consent_source_bundled.format(
                tool=res.display_name
            )
        self._warning.setText(warning_text)
        self._warning.setVisible(bool(warning_text))

        self._accept_btn.setEnabled(False)
        if res.is_html:
            self._browser.setHtml(res.text)
        else:
            self._browser.setPlainText(res.text)
        self._browser.verticalScrollBar().setValue(0)
        QTimer.singleShot(0, self._maybe_enable_accept)

    def _maybe_enable_accept(self, *args):
        bar = self._current_browser().verticalScrollBar()
        at_bottom = bar.maximum() == 0 or bar.value() >= bar.maximum()
        self._accept_btn.setEnabled(at_bottom)

    def _accept_current(self):
        idx = self._current_index
        if idx < len(self._licenses) - 1:
            self._current_index = idx + 1
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
