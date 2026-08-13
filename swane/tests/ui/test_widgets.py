"""Head-less tests for the standalone SWANe UI widgets.

Qt runs with ``QT_QPA_PLATFORM=offscreen`` (set in conftest), so no display is
required. Every widget is registered with ``qtbot`` for deterministic cleanup.
"""

import swane_supplement
from PySide6.QtWidgets import QTreeWidget
from PySide6.QtCore import Qt

from swane.ui.VerticalScrollArea import VerticalScrollArea
from swane.ui.PersistentProgressDialog import PersistentProgressDialog
from swane.ui.CustomTreeWidgetItem import CustomTreeWidgetItem
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
        from swane import strings

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
        item.set_art(swane_supplement.okIcon_file)
        assert item.get_status() == WorkflowSignals.NODE_COMPLETED
        item.set_art(swane_supplement.errorIcon_file)
        assert item.get_status() == WorkflowSignals.NODE_ERROR
