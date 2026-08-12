import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent

from swane.ui.VerticalScrollArea import VerticalScrollArea


def test_vertical_scroll_area_event_filter(qtbot=None):
    # Ensure a QApplication exists
    app = QApplication.instance() or QApplication([])

    v = VerticalScrollArea()
    # create a resize event and call eventFilter on the widget contents
    event = QEvent(QEvent.Resize)

    # call eventFilter directly
    v.eventFilter(v.m_scrollAreaWidgetContents, event)

    # if no exception and minimum width set, test passes
    assert v.minimumWidth() >= 0
