from PySide6.QtWidgets import (QTabBar, QStylePainter, QStyle, QStyleOptionTab, QTabWidget, QProxyStyle,
                               QStyleOptionTabWidgetFrame, QApplication)
from PySide6 import QtCore


class VerticalTabWidget(QTabWidget):
    def __init__(self, width, height):
        super(VerticalTabWidget, self).__init__()
        self.setTabBar(VerticalTabBar())
        self.setTabPosition(QTabWidget.West)

    def initStyleOption(self, option):
        super(VerticalTabWidget, self).initStyleOption(option)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionTabWidgetFrame()
        self.initStyleOption(option)
        option.rect = QtCore.QRect(QtCore.QPoint(self.tabBar().geometry().width(), 0),
                          QtCore.QSize(option.rect.width(), option.rect.height()))
        painter.drawPrimitive(QStyle.PE_FrameTabWidget, option)


class VerticalTabBar(QTabBar):
    def __init__(self, *args, **kwargs):
        super(VerticalTabBar, self).__init__(*args, **kwargs)
        self.setDrawBase(False)
        self.setElideMode(QtCore.Qt.ElideNone)

    def initStyleOption(self, option, index):
        super(VerticalTabBar, self).initStyleOption(option, index)
        if QApplication.style().objectName() != "fusion":
            option.shape = QTabBar.RoundedNorth
            option.position = QStyleOptionTab.Beginning

    def tabSizeHint(self, index):
        sizeHint = super(VerticalTabBar, self).tabSizeHint(index)
        sizeHint.transpose()
        return sizeHint

    def paintEvent(self, event):
        if QApplication.style().objectName() == "fusion":
            painter = QStylePainter(self)
            option = QStyleOptionTab()
            for index in range(self.count()):
                self.initStyleOption(option, index)
                painter.drawControl(QStyle.CE_TabBarTabShape, option)
                painter.drawText(self.tabRect(index),
                                 QtCore.Qt.AlignCenter | QtCore.Qt.TextDontClip,
                                 self.tabText(index))
        else:
            super(VerticalTabBar, self).paintEvent(event)

