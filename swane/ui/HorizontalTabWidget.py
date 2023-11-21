from PySide6.QtWidgets import (QTabBar, QStylePainter, QStyle, QStyleOptionTab, QTabWidget)
from PySide6 import QtCore


class HorizontalTabWidget(QTabWidget):
    def __init__(self, width, height):
        super(HorizontalTabWidget, self).__init__()
        self.setTabBar(HorizontalTabBar(width=width, height=height))
        self.setTabPosition(QTabWidget.West)


class HorizontalTabBar(QTabBar):
    def __init__(self, *args, **kwargs):
        self.tabSize = QtCore.QSize(kwargs.pop('width'), kwargs.pop('height'))
        super(HorizontalTabBar, self).__init__(*args, **kwargs)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionTab()

        for index in range(self.count()):
            self.initStyleOption(option, index)
            tabRect = self.tabRect(index)
            tabRect.moveLeft(10)
            painter.drawControl(QStyle.CE_TabBarTabShape, option)
            painter.drawText(tabRect, QtCore.Qt.AlignVCenter | QtCore.Qt.TextDontClip, self.tabText(index))

    def tabSizeHint(self, index):
        return self.tabSize