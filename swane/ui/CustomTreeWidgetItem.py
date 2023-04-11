from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QTreeWidgetItem, QSpacerItem
from PySide6.QtSvgWidgets import QSvgWidget


class CustomTreeWidgetItem(QTreeWidgetItem):

    def __init__(self, parent, tree, text, art=None):
        super(CustomTreeWidgetItem, self).__init__(parent)
        
        self.widget = QWidget()
        self.widget.setLayout(QHBoxLayout())
        self.artLabel = QSvgWidget()
        self.artLabel.setFixedWidth(26)
        self.artLabel.setFixedHeight(26)
        self.setArt(art)
        self.textLabel = QLabel(text)
        self.resize_text_label()
        
        self.widget.layout().addWidget(self.artLabel)
        self.widget.layout().addWidget(self.textLabel)
        self.widget.layout().addSpacerItem(QSpacerItem(25, 0))

        tree.setItemWidget(self, 0, self.widget)
        
        self.completed = False
        self.art = None
        
    def setText(self, text):
        self.textLabel.setText(text)
        self.resize_text_label()

    def resize_text_label(self):
        self.textLabel.setMinimumWidth(self.textLabel.fontMetrics().boundingRect(self.textLabel.text()).width() + 10)
        
    def getText(self):
        return self.textLabel.text()
    
    def setArt(self, art):
        self.art = art
        if art is not None:
            self.artLabel.load(art)
