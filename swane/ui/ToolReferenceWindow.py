from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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

from swane.utils.ToolReference import Package
from swane.utils.ToolReference import ToolReference


class ToolReferenceWindow(QDialog):
    """
    Custom implementation of PySide QDialog to show SWANe tool encyclopedia.

    The dialog displays tools grouped by package (FSL, FreeSurfer, Other) using
    lateral tabs. Each tab includes a search bar to filter tools by key/command/url.

    Parameters
    ----------
    nipype_database : Dict[str, ToolReference]
        Dictionary that maps a tool key (e.g., "BET") to its ToolReference metadata.
    parent : QWidget, optional
        Parent widget.

    Returns
    -------
    None.
    """

    def __init__(self, nipype_database: Dict[str, ToolReference], parent=None):
        super(ToolReferenceWindow, self).__init__(parent)

        self._db = nipype_database

        # Cache per package: (search_lineedit, list_container, list_layout, cards[(key, card_widget, search_blob)])
        self._package_ui: Dict[Package, Tuple[QLineEdit, QWidget, QVBoxLayout, List[Tuple[str, QWidget, str]]]] = {}

        self.setWindowTitle("Tool Encyclopedia")

        layout = QVBoxLayout()

        tab_widget = VerticalQTabWidget(force_top_valign=True)
        tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Create one tab per package in fixed order (nice UX)
        for pkg in (Package.FSL, Package.FREESURFER, Package.OTHER):
            tab = self._build_package_tab(pkg)
            tab_widget.addTab(tab, pkg.value.upper() if pkg != Package.OTHER else "OTHER")

        layout.addWidget(tab_widget)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        self.setLayout(layout)

        # Initial filter = show all
        for pkg in self._package_ui:
            self._apply_filter(pkg, "")

    def _build_package_tab(self, package: Package) -> QWidget:
        """
        Build a single tab for a given package.

        Parameters
        ----------
        package : Package
            The package enum value (FSL, FREESURFER, OTHER).

        Returns
        -------
        QWidget
            The constructed tab widget for the selected package.
        """
        tab = QWidget()
        tab_lay = QVBoxLayout()
        tab.setLayout(tab_lay)

        # --- Search row
        search_row = QHBoxLayout()
        search_label = QLabel("Search:")
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Type to filter (key, command, url, references)...")
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(80)

        search_row.addWidget(search_label)
        search_row.addWidget(search_edit, 1)
        search_row.addWidget(clear_btn)
        tab_lay.addLayout(search_row)

        # --- Scroll area with cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_lay = QVBoxLayout()
        scroll_lay.setAlignment(Qt.AlignTop)
        scroll_content.setLayout(scroll_lay)
        scroll.setWidget(scroll_content)

        tab_lay.addWidget(scroll)

        # Build cards for package
        cards: List[Tuple[str, QWidget, str]] = []
        tools = self._get_tools_by_package(package)

        for key, ref in tools:
            card = self._make_tool_card(key, ref)
            scroll_lay.addWidget(card)

            # precomputed searchable string (lower) for fast filtering
            blob = self._make_search_blob(key, ref)
            cards.append((key, card, blob))

        # Spacer to keep cards on top
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_lay.addWidget(spacer)

        # Save UI references
        self._package_ui[package] = (search_edit, scroll_content, scroll_lay, cards)

        # Connect search events
        search_edit.textChanged.connect(lambda text, pkg=package: self._apply_filter(pkg, text))
        clear_btn.clicked.connect(lambda _=False, se=search_edit: se.setText(""))

        return tab

    def _get_tools_by_package(self, package: Package) -> List[Tuple[str, ToolReference]]:
        """
        Extract and sort tools belonging to a specific package.

        Parameters
        ----------
        package : Package
            Package to filter tools by.

        Returns
        -------
        List[Tuple[str, ToolReference]]
            Sorted list of (tool_key, ToolReference) for the selected package.
        """
        items = [(k, v) for k, v in self._db.items() if v.package == package]
        items.sort(key=lambda kv: kv[0].lower())
        return items

    def _make_search_blob(self, key: str, ref: ToolReference) -> str:
        """
        Create a lowercase string used for searching/filtering a tool card.

        Parameters
        ----------
        key : str
            Dictionary key of the tool (e.g., "BET").
        ref : ToolReference
            Tool reference info.

        Returns
        -------
        str
            Lowercase concatenated searchable content.
        """
        parts = [key, ref.command, ref.url]
        parts.extend(ref.references or [])
        return " ".join(parts).lower()

    def _apply_filter(self, package: Package, text: str) -> None:
        """
        Filter visible tool cards for a given package tab.

        Parameters
        ----------
        package : Package
            Package tab to apply filter to.
        text : str
            Filter text.

        Returns
        -------
        None.
        """
        text = (text or "").strip().lower()
        _, _, _, cards = self._package_ui[package]

        for _, card, blob in cards:
            card.setVisible(text == "" or text in blob)

    def _make_tool_card(self, key: str, ref: ToolReference) -> QWidget:
        """
        Build a "card-like" widget describing a tool.

        Parameters
        ----------
        key : str
            Tool key in the dictionary.
        ref : ToolReference
            Tool reference info.

        Returns
        -------
        QWidget
            Card widget containing tool metadata.
        """
        outer = QFrame()
        outer.setFrameShape(QFrame.StyledPanel)
        outer.setFrameShadow(QFrame.Raised)
        outer.setStyleSheet(
            """
            QFrame {
                border: 1px solid #d0d0d0;
                border-radius: 8px;
                padding: 8px;
                background: white;
            }
            """
        )

        lay = QVBoxLayout()
        lay.setSpacing(6)
        outer.setLayout(lay)

        # Title row: KEY + command
        title = QLabel(f"<b>{key}</b>  <span style='color:#555;'>({ref.command})</span>")
        title.setTextFormat(Qt.RichText)
        lay.addWidget(title)

        # URL row
        url_label = QLabel(
            f"<a href='{ref.url}' style='text-decoration:none;'>{ref.url}</a>"
        )
        url_label.setTextFormat(Qt.RichText)
        url_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        url_label.setOpenExternalLinks(True)  # simplest (Qt handles it)
        lay.addWidget(url_label)

        # References
        if ref.references:
            ref_title = QLabel("<b>References</b>")
            ref_title.setTextFormat(Qt.RichText)
            lay.addWidget(ref_title)

            for i, r in enumerate(ref.references, start=1):
                # light formatting, keep it readable
                r_lab = QLabel(f"{i}. {r}")
                r_lab.setWordWrap(True)
                r_lab.setStyleSheet("color: #333;")
                lay.addWidget(r_lab)
        else:
            no_ref = QLabel("<i>No references available.</i>")
            no_ref.setTextFormat(Qt.RichText)
            no_ref.setStyleSheet("color: #666;")
            lay.addWidget(no_ref)

        return outer
