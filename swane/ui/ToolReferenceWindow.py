from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QScrollArea,
    QSizePolicy,
)

from PySide6_VerticalQTabWidget import VerticalQTabWidget

from swane import strings
from swane.utils.ToolReference import Package, tool_reference_list
from swane.utils.ToolReference import ToolReference


class ToolReferenceWindow(QDialog):
    """
    Custom implementation of PySide QDialog to show SWANe tool encyclopedia.
    """

    def __init__(self, default_tab=None, search_string=None, parent=None):
        super().__init__(parent)

        self._db = tool_reference_list
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setWindowModality(Qt.NonModal)
        self.setModal(False)

        # Cache per package:
        # (search_lineedit, list_container, list_layout, cards[(key, widget, search_blob)])
        self._package_ui: Dict[
            Package,
            Tuple[
                QWidget,
                QVBoxLayout,
                List[Tuple[str, QWidget, str]],
                QLabel,  # no_results placeholder
            ],
        ] = {}

        self.setWindowTitle(strings.toolreference_title)

        layout = QVBoxLayout(self)

        # --- Global search bar (above tabs)
        search_row = QHBoxLayout()
        search_label = QLabel(strings.toolreference_search_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(strings.toolreference_search_hint)
        clear_btn = QPushButton(strings.toolreference_clear_btn)
        clear_btn.setFixedWidth(80)

        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(clear_btn)
        layout.addLayout(search_row)

        self._tab_widget = VerticalQTabWidget(force_top_valign=True)
        self._tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        for idx, pkg in enumerate((Package.FSL, Package.FREESURFER, Package.OTHER)):
            tab = self._build_package_tab(pkg)
            self._tab_widget.addTab(tab, pkg.value.upper())
            if pkg == default_tab:
                self._tab_widget.setCurrentIndex(idx)

        layout.addWidget(self._tab_widget)

        close_button = QPushButton(strings.toolreference_close_btn)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        # Initial filter
        for pkg in self._package_ui:
            self._apply_filter(pkg, "")

        self.search_edit.textChanged.connect(self._apply_global_filter)
        clear_btn.clicked.connect(lambda: self.search_edit.setText(""))
        if search_string:
            self.search_edit.setText(search_string)

    # ------------------------------------------------------------------

    def search(self, tab: Package, string):
        for i in range(self._tab_widget.count()):
            if self._tab_widget.tabText(i) == tab.value.upper():
                self._tab_widget.setCurrentIndex(i)
        self.search_edit.setText(string)

    def _apply_global_filter(self, text: str) -> None:
        for pkg in self._package_ui:
            self._apply_filter(pkg, text)

    def _build_package_tab(self, package: Package) -> QWidget:
        tab = QWidget()
        tab_lay = QVBoxLayout(tab)
        tab_lay.setContentsMargins(1, 1, 1, 1)
        tab_lay.setSpacing(0)

        # --- Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setAlignment(Qt.AlignTop)
        scroll_lay.setContentsMargins(8, 8, 8, 8)  # solo padding interno
        scroll_lay.setSpacing(8)

        scroll.setWidget(scroll_content)

        tab_lay.addWidget(scroll)

        # Build entries
        cards: List[Tuple[str, QWidget, str]] = []
        tools = self._get_tools_by_package(package)

        for key, ref in tools:
            widget = self._make_tool_entry(key, ref)
            scroll_lay.addWidget(widget)

            blob = self._make_search_blob(key, ref)
            cards.append((key, widget, blob))

        # --- No results placeholder
        no_results = QLabel(strings.toolreference_no_results)
        no_results.setAlignment(Qt.AlignCenter)
        no_results.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #777;
                margin-top: 20px;
            }
            """)
        no_results.setVisible(False)
        scroll_lay.addWidget(no_results)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_lay.addWidget(spacer)

        self._package_ui[package] = (scroll_content, scroll_lay, cards, no_results)

        return tab

    # ------------------------------------------------------------------

    def _get_tools_by_package(
        self, package: Package
    ) -> List[Tuple[str, ToolReference]]:
        items = [(k, v) for k, v in self._db.items() if v.package == package]
        items.sort(key=lambda kv: kv[1].command.lower())
        return items

    # ------------------------------------------------------------------

    def _make_search_blob(self, key: str, ref: ToolReference) -> str:
        # we only want filter by command name
        return ref.command.lower()

    # ------------------------------------------------------------------

    def _apply_filter(self, package: Package, text: str) -> None:
        text = (text or "").strip().lower()
        _, _, cards, no_results = self._package_ui[package]

        visible_count = 0

        for _, widget, blob in cards:
            visible = text == "" or text in blob
            widget.setVisible(visible)
            if visible:
                visible_count += 1

        no_results.setVisible(visible_count == 0)

    # ------------------------------------------------------------------

    def _make_tool_entry(self, key: str, ref: ToolReference) -> QWidget:
        """
        Flat, document-like tool entry (no cards, no sub-frames).
        """

        card = QFrame()
        card.setObjectName("toolCard")
        card.setStyleSheet("""
            QFrame#toolCard {
                background: #f9f9f9;
                border: 1px solid #dddddd;
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            """)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        # --- Command header (top level)
        cmd_label = QLabel(ref.command)
        cmd_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #111;
            }
            """)
        lay.addWidget(cmd_label)

        # --- URL (secondary metadata)
        url_label = QLabel(
            f"<a href='{ref.url}' style='text-decoration:none;'>{ref.url}</a>"
        )
        url_label.setTextFormat(Qt.RichText)
        url_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        url_label.setOpenExternalLinks(True)
        url_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                margin-top: 6px;
                color: #555;
            }
            """)
        lay.addWidget(url_label)

        # --- References section
        if ref.references:
            ref_title = QLabel(strings.toolreference_reference_label)
            ref_title.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    font-weight: 600;
                    margin-top: 6px;
                    color: #222;
                }
                """)
            lay.addWidget(ref_title)

            for i, r in enumerate(ref.references, start=1):
                r_lab = QLabel(f"{i}. {r}")
                r_lab.setWordWrap(True)
                r_lab.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        margin-left: 12px;
                        color: #333;
                    }
                    """)
                lay.addWidget(r_lab)

        return card
