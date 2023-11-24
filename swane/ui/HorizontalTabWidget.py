from PySide6.QtWidgets import (QTabBar, QStylePainter, QStyle, QStyleOptionTab, QTabWidget, QProxyStyle)
from PySide6 import QtCore


class HorizontalTabWidget(QTabWidget):
    def __init__(self, width, height):
        super(HorizontalTabWidget, self).__init__()
        # self.setTabBar(HorizontalTabBar(width=width, height=height))
        #self.setTabBar(HorizontalTabBar())
        self.tabBar().setStyle(CustomTabStyle())
        self.setTabPosition(QTabWidget.West)

# class HorizontalTabBar(QTabBar):
#     def __init__(self, *args, **kwargs):
#         self.tabSize = QtCore.QSize(kwargs.pop('width'), kwargs.pop('height'))
#         super(HorizontalTabBar, self).__init__(*args, **kwargs)
#
#     def paintEvent(self, event):
#         painter = QStylePainter(self)
#         option = QStyleOptionTab()
#
#         for index in range(self.count()):
#             self.initStyleOption(option, index)
#             tabRect = self.tabRect(index)
#             tabRect.moveLeft(10)
#             painter.drawControl(QStyle.CE_TabBarTabShape, option)
#             painter.drawText(tabRect, QtCore.Qt.AlignVCenter | QtCore.Qt.TextDontClip, self.tabText(index))
#
#     def tabSizeHint(self, index):
#         return self.tabSize


class CustomTabStyle(QProxyStyle):
    def sizeFromContents(self, ctype, option, size, widget=None):
        s = super(CustomTabStyle, self).sizeFromContents(ctype, option, size, widget)
        if ctype == QStyle.CT_TabBarTab:
            s.transpose()
        return s

    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.CE_TabBarTabLabel:
            my_style_option_tab = QStyleOptionTab(option)
            if my_style_option_tab:
                my_style_option_tab.shape = QTabBar.RoundedNorth
                super(CustomTabStyle, self).drawControl(element, my_style_option_tab, painter, widget)
            return
        super(CustomTabStyle, self).drawControl(element, option, painter, widget)


class HorizontalTabBar(QTabBar):
    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionTab()
        for index in range(self.count()):
            self.initStyleOption(option, index)
            painter.drawControl(QStyle.CE_TabBarTabShape, option)
            painter.drawText(self.tabRect(index),
                             QtCore.Qt.AlignCenter | QtCore.Qt.TextDontClip,
                             self.tabText(index))

    def tabSizeHint(self, index):
        size = QTabBar.tabSizeHint(self, index)
        if size.width() < size.height():
            size.transpose()
        return size
