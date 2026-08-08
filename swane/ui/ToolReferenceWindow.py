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
    Custom QDialog implementation showing the SWANe tool encyclopedia.

    Tools are grouped by package and displayed in dedicated vertical tabs.
    A global search field allows filtering tools by command name.
    """

    def __init__(
        self,
        default_tab: Package | None = None,
        search_string: str | None = None,
        parent: QWidget | None = None,
    ):
        """
        Initialize the tool reference window.

        Parameters
        ----------
        default_tab : Package, optional
            Package tab to select when the window is opened.
        search_string : str, optional
            Initial string used to filter the available tools.
        parent : QWidget, optional
            Parent widget of the dialog.
        """
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
        # (
        #     scroll_content,
        #     scroll_layout,
        #     cards[(key, widget, search_blob)],
        #     no_results_label,
        # )
        self._package_ui: Dict[
            Package,
            Tuple[
                QWidget,
                QVBoxLayout,
                List[Tuple[str, QWidget, str]],
                QLabel,
            ],
        ] = {}

        self.setWindowTitle(strings.toolreference_title)

        layout = QVBoxLayout(self)

        # --- Global search bar
        search_row = QHBoxLayout()

        search_label = QLabel(strings.toolreference_search_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(strings.toolreference_search_hint)

        self.clear_btn = QPushButton(strings.toolreference_clear_btn)
        self.clear_btn.setFixedWidth(80)
        self.clear_btn.setEnabled(False)

        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.clear_btn)

        layout.addLayout(search_row)

        # --- Package tabs
        self._tab_widget = VerticalQTabWidget(force_top_valign=True)
        self._tab_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        for idx, pkg in enumerate(
            (Package.FSL, Package.FREESURFER, Package.OTHER)
        ):
            tab = self._build_package_tab(pkg)
            self._tab_widget.addTab(tab, pkg.value.upper())

            if pkg == default_tab:
                self._tab_widget.setCurrentIndex(idx)

        layout.addWidget(self._tab_widget)

        # --- Close button
        close_button = QPushButton(strings.toolreference_close_btn)
        close_button.clicked.connect(self.close)

        layout.addWidget(close_button)

        # Apply the initial empty filter.
        for pkg in self._package_ui:
            self._apply_filter(pkg, "")

        # Search signals.
        self.search_edit.textChanged.connect(self._apply_global_filter)
        self.search_edit.textChanged.connect(self._update_clear_button)

        self.clear_btn.clicked.connect(self.search_edit.clear)

        if search_string:
            self.search_edit.setText(search_string)

    def search(self, tab: Package, string: str) -> None:
        """
        Select a package tab and apply a search string.

        Parameters
        ----------
        tab : Package
            Package tab to activate.
        string : str
            Search text to apply to the tool list.

        Returns
        -------
        None
        """
        for i in range(self._tab_widget.count()):
            if self._tab_widget.tabText(i) == tab.value.upper():
                self._tab_widget.setCurrentIndex(i)
                break

        self.search_edit.setText(string)

    def _apply_global_filter(self, text: str) -> None:
        """
        Apply the current search text to every package tab.

        Parameters
        ----------
        text : str
            Text entered in the global search field.

        Returns
        -------
        None
        """
        for pkg in self._package_ui:
            self._apply_filter(pkg, text)

    def _update_clear_button(self, text: str) -> None:
        """
        Update the enabled state of the search clear button.

        The clear button is enabled only when the search field contains
        at least one non-whitespace character.

        Parameters
        ----------
        text : str
            Current content of the search field.

        Returns
        -------
        None
        """
        self.clear_btn.setEnabled(bool(text.strip()))

    def _build_package_tab(self, package: Package) -> QWidget:
        """
        Build the tool list tab for a package.

        Parameters
        ----------
        package : Package
            Package whose tools must be displayed in the tab.

        Returns
        -------
        QWidget
            Widget containing the scrollable list of tools belonging to
            the requested package.
        """
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
        scroll_lay.setContentsMargins(8, 8, 8, 8)
        scroll_lay.setSpacing(8)

        scroll.setWidget(scroll_content)
        tab_lay.addWidget(scroll)

        # --- Tool entries
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
        no_results.setStyleSheet(
            """
            QLabel {
                font-size: 13px;
                color: #777;
                margin-top: 20px;
            }
            """
        )
        no_results.setVisible(False)

        scroll_lay.addWidget(no_results)

        # --- Expanding spacer
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        scroll_lay.addWidget(spacer)

        self._package_ui[package] = (
            scroll_content,
            scroll_lay,
            cards,
            no_results,
        )

        return tab

    def _get_tools_by_package(
        self,
        package: Package,
    ) -> List[Tuple[str, ToolReference]]:
        """
        Return tool references belonging to a package.

        Tools are sorted alphabetically by command name.

        Parameters
        ----------
        package : Package
            Package used to filter the tool reference database.

        Returns
        -------
        List[Tuple[str, ToolReference]]
            List of tool database keys and corresponding tool references.
        """
        items = [
            (key, ref)
            for key, ref in self._db.items()
            if ref.package == package
        ]

        items.sort(key=lambda item: item[1].command.lower())

        return items

    def _make_search_blob(
        self,
        key: str,
        ref: ToolReference,
    ) -> str:
        """
        Build the searchable text associated with a tool.

        Currently only the command name is included in the search index.

        Parameters
        ----------
        key : str
            Tool database key. Reserved for possible future search fields.
        ref : ToolReference
            Tool reference whose searchable representation must be built.

        Returns
        -------
        str
            Lowercase searchable command name.
        """
        return ref.command.lower()

    def _apply_filter(
        self,
        package: Package,
        text: str,
    ) -> None:
        """
        Filter the displayed tools of a package.

        Tool entries whose command name does not contain the search text
        are hidden. When no matching tools remain, the no-results label is
        displayed.

        Parameters
        ----------
        package : Package
            Package whose tool widgets must be filtered.
        text : str
            Search text used to determine visible tool entries.

        Returns
        -------
        None
        """
        text = (text or "").strip().lower()

        _, _, cards, no_results = self._package_ui[package]

        visible_count = 0

        for _, widget, blob in cards:
            visible = text == "" or text in blob

            widget.setVisible(visible)

            if visible:
                visible_count += 1

        no_results.setVisible(visible_count == 0)

    def _make_tool_entry(
        self,
        key: str,
        ref: ToolReference,
    ) -> QWidget:
        """
        Build the widget representing a single tool reference.

        The entry contains the command name, the external documentation URL
        and, when available, the associated bibliographic references.

        Parameters
        ----------
        key : str
            Tool database key. Currently not displayed but preserved as part
            of the tool-entry construction interface.
        ref : ToolReference
            Tool reference to display.

        Returns
        -------
        QWidget
            Widget containing the formatted tool information.
        """
        card = QFrame()
        card.setObjectName("toolCard")
        card.setStyleSheet(
            """
            QFrame#toolCard {
                background: #f9f9f9;
                border: 1px solid #dddddd;
                border-radius: 8px;
            }

            QLabel {
                background: transparent;
                border: none;
            }
            """
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        # --- Command header
        cmd_label = QLabel(ref.command)
        cmd_label.setStyleSheet(
            """
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #111;
            }
            """
        )

        lay.addWidget(cmd_label)

        # --- Documentation URL
        url_label = QLabel(
            f"<a href='{ref.url}' style='text-decoration:none;'>"
            f"{ref.url}</a>"
        )
        url_label.setTextFormat(Qt.RichText)
        url_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        url_label.setOpenExternalLinks(True)
        url_label.setStyleSheet(
            """
            QLabel {
                font-size: 14px;
                font-weight: 600;
                margin-top: 6px;
                color: #555;
            }
            """
        )

        lay.addWidget(url_label)

        # --- References section
        if ref.references:
            ref_title = QLabel(strings.toolreference_reference_label)
            ref_title.setStyleSheet(
                """
                QLabel {
                    font-size: 14px;
                    font-weight: 600;
                    margin-top: 6px;
                    color: #222;
                }
                """
            )

            lay.addWidget(ref_title)

            for i, reference in enumerate(ref.references, start=1):
                reference_label = QLabel(f"{i}. {reference}")
                reference_label.setWordWrap(True)
                reference_label.setStyleSheet(
                    """
                    QLabel {
                        font-size: 12px;
                        margin-left: 12px;
                        color: #333;
                    }
                    """
                )

                lay.addWidget(reference_label)

        return card