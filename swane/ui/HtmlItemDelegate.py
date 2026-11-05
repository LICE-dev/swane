from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtGui import QPainter, QPalette, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)


class HtmlItemDelegate(QStyledItemDelegate):
    """
    Custom item delegate that renders HTML-formatted rich text in view items.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """
        Renders the item using QTextDocument to format HTML tags.

        Parameters
        ----------
        painter : QPainter
            The painter used to render the item.
        option : QStyleOptionViewItem
            The style options for the item.
        index : QModelIndex
            The model index of the item.
        """
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        painter.save()
        doc = QTextDocument()
        doc.setDefaultFont(options.font)

        # Apply palette text color (selected vs unselected)
        if options.state & QStyle.StateFlag.State_Selected:
            color = options.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText
            )
        else:
            color = options.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.Text
            )
        doc.setDefaultStyleSheet(f"* {{ color: {color.name()}; }}")
        doc.setHtml(options.text)

        # Clear text so standard control drawing draws background/selection without text
        options.text = ""
        widget = options.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, options, painter, widget
        )

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, options, widget
        )
        painter.translate(text_rect.topLeft())
        painter.setClipRect(0, 0, text_rect.width(), text_rect.height())

        # Center vertically inside text_rect if height allows
        doc_height = doc.size().height()
        if text_rect.height() > doc_height:
            v_offset = (text_rect.height() - doc_height) / 2
            painter.translate(0, v_offset)

        doc.drawContents(painter)
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        """
        Calculates the size required to render the HTML item.

        Parameters
        ----------
        option : QStyleOptionViewItem
            The style options for the item.
        index : QModelIndex
            The model index of the item.

        Returns
        -------
        QSize
            The computed size hint.
        """
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        doc = QTextDocument()
        doc.setDefaultFont(options.font)
        doc.setHtml(options.text)

        # Clear text so the style sizes the item from the rendered document, not the raw HTML source
        options.text = ""
        widget = options.widget
        style = widget.style() if widget else QApplication.style()
        size = style.sizeFromContents(
            QStyle.ContentsType.CT_ItemViewItem,
            options,
            QSize(int(doc.idealWidth()), int(doc.size().height())),
            widget,
        )
        return size
