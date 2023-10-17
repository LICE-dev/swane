from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QTreeWidgetItem, QSpacerItem
from PySide6.QtSvgWidgets import QSvgWidget
from swane.utils import print_error

class CustomTreeWidgetItem(QTreeWidgetItem):
    """
    Custom implementation of PySide QTreeWidgetItem to define the Workflows Tree items.

    """

    def __init__(self, parent, tree, text, art=None):
        super(CustomTreeWidgetItem, self).__init__(parent)
        
        self.widget = QWidget()
        self.widget.setLayout(QHBoxLayout())
        self.artLabel = QSvgWidget()
        self.artLabel.setFixedWidth(26)
        self.artLabel.setFixedHeight(26)
        self.set_art(art)
        self.textLabel = QLabel(text)
        self.resize_text_label()
        
        self.widget.layout().addWidget(self.artLabel)
        self.widget.layout().addWidget(self.textLabel)
        self.widget.layout().addSpacerItem(QSpacerItem(25, 0))

        tree.setItemWidget(self, 0, self.widget)
        
        self.completed = False
        self.art = None


    def setText(self, text: str):
        """
        Set the tree item text.

        Parameters
        ----------
        text : str
            The item text.

        Returns
        -------
        None.

        """
        
        try:
            self.textLabel.setText(text)
            self.resize_text_label()
        except:
            print_error()


    def resize_text_label(self):
        """
        Resize the tree item label.
        Allow the horizontal scroll when expanding subsection.

        Returns
        -------
        None.

        """
        
        try:
            self.textLabel.setMinimumWidth(self.textLabel.fontMetrics().boundingRect(self.textLabel.text()).width() + 10)
        except:
            print_error()


    def get_text(self) -> str:
        """
        Get the tree item text from its label.

        Returns
        -------
        str
            The item text.

        """
        
        try:
            return self.textLabel.text()
        except:
            print_error()
    

    def set_art(self, art: str):
        """
        Set the icon of the tree item.

        Parameters
        ----------
        art : str
            The icon path of the tree item.

        Returns
        -------
        None.

        """

        try:
            self.art = art
            
            if art is not None:
                self.artLabel.load(art)
        except:
            print_error()
