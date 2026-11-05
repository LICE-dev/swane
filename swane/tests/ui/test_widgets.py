"""Head-less tests for the standalone SWANe UI widgets.

Qt runs with ``QT_QPA_PLATFORM=offscreen`` (set in conftest), so no display is
required. Every widget is registered with ``qtbot`` for deterministic cleanup.
"""

import pytest

from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:
    pytest.skip(
        "no working Qt binding (PySide6) — GUI tests skipped",
        allow_module_level=True,
    )

from swane import resources
from PySide6.QtWidgets import QTreeWidget
from PySide6.QtCore import Qt

from swane.ui.VerticalScrollArea import VerticalScrollArea
from swane.ui.PersistentProgressDialog import PersistentProgressDialog
from swane.ui.CustomTreeWidgetItem import CustomTreeWidgetItem
from swane.ui.HtmlItemDelegate import HtmlItemDelegate
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowSignals


def test_vertical_scroll_area(qtbot):
    area = VerticalScrollArea()
    qtbot.addWidget(area)
    assert area.widgetResizable() is True
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert area.widget() is area.m_scrollAreaWidgetContents


class TestPersistentProgressDialog:

    def test_increase_value_sets_maximum_lazily(self, qtbot):
        dialog = PersistentProgressDialog("working", 0, 0)
        qtbot.addWidget(dialog)
        # maximum starts at 0 and is lazily set on the first increase
        dialog.increase_value(1, maximum=5)
        assert dialog.maximum() == 5
        # value must never move backwards across successive increases
        before = dialog.value()
        dialog.increase_value(2)
        assert dialog.value() >= before

    def test_close_event_is_ignored(self, qtbot):
        dialog = PersistentProgressDialog("working", 0, 10)
        qtbot.addWidget(dialog)
        dialog.show()
        dialog.close()
        # closeEvent ignores the request, so the dialog stays visible
        assert dialog.isVisible() is True


class TestCustomTreeWidgetItem:

    def test_text_and_tooltip_infochar(self, qtbot):
        from swane.resources import strings

        tree = QTreeWidget()
        qtbot.addWidget(tree)
        item = CustomTreeWidgetItem(tree, tree, "Node", "node_name")

        assert item.get_text() == "Node"
        item.setToolTip(0, "some tooltip")
        assert item.get_text().endswith(strings.INFOCHAR)
        item.setToolTip(0, "")
        assert not item.get_text().endswith(strings.INFOCHAR)

    def test_status_from_art(self, qtbot):
        tree = QTreeWidget()
        qtbot.addWidget(tree)
        item = CustomTreeWidgetItem(tree, tree, "Node", "node_name")

        assert item.get_status() is None
        item.set_art(resources.okIcon_file)
        assert item.get_status() == WorkflowSignals.NODE_COMPLETED
        item.set_art(resources.errorIcon_file)
        assert item.get_status() == WorkflowSignals.NODE_ERROR


class TestHtmlItemDelegate:

    def test_html_delegate_paints_and_sizes(self, qtbot):
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyleOptionViewItem
        from PySide6.QtGui import QPixmap, QPainter

        list_widget = QListWidget()
        qtbot.addWidget(list_widget)
        delegate = HtmlItemDelegate(list_widget)
        list_widget.setItemDelegate(delegate)

        item = QListWidgetItem("Subject - MR - <b>T1</b>: 176 images, 1 volume")
        list_widget.addItem(item)

        option = QStyleOptionViewItem()
        option.rect = list_widget.visualItemRect(item)
        size_hint = delegate.sizeHint(option, list_widget.model().index(0, 0))
        assert size_hint.isValid()
        assert size_hint.width() > 0
        assert size_hint.height() > 0

        # Tags must be consumed: the hint matches the same text without markup
        plain_item = QListWidgetItem("Subject - MR - T1: 176 images, 1 volume")
        list_widget.addItem(plain_item)
        plain_hint = delegate.sizeHint(option, list_widget.model().index(1, 0))
        assert abs(size_hint.width() - plain_hint.width()) < 10  # bold only

        # Test rendering without errors
        pixmap = QPixmap(max(size_hint.width(), 100), max(size_hint.height(), 30))
        painter = QPainter(pixmap)
        option.rect = pixmap.rect()
        delegate.paint(painter, option, list_widget.model().index(0, 0))
        painter.end()

        # Test rendering selected state
        from PySide6.QtWidgets import QStyle

        painter = QPainter(pixmap)
        option.state |= QStyle.StateFlag.State_Selected
        delegate.paint(painter, option, list_widget.model().index(0, 0))
        painter.end()
