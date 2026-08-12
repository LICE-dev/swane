import pytest
from PySide6.QtWidgets import QApplication
from swane.ui.PersistentProgressDialog import PersistentProgressDialog


def test_persistent_progress_dialog_minimal(qtbot):
    app = QApplication.instance() or QApplication([])
    dlg = PersistentProgressDialog(None)
    dlg.setWindowTitle('test')
    dlg.show()
    assert dlg.windowTitle() == 'test'
    dlg.close()
