import os
import subprocess
import sys


def test_full_gui_startup_path_avoids_nipype_and_scipy():
    """Verify in a clean Python interpreter that importing the GUI entry points
    and constructing QApplication and ConfigManager does not load Nipype or SciPy."""
    code = (
        "import sys, os\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "import swane\n"
        "from swane.config.ConfigManager import ConfigManager\n"
        "from swane.utils.DependencyManager import DependencyManager\n"
        "from swane.ui.MainWindow import MainWindow\n"
        "assert 'nipype' not in sys.modules, f'Nipype leaked: {sys.modules.get(\"nipype\")}'\n"
        "assert 'scipy' not in sys.modules, f'SciPy leaked: {sys.modules.get(\"scipy\")}'\n"
        # Only needed for DICOM scans, mail and encrypted preferences
        "for mod in ('pydicom', 'numpy', 'cryptography', 'smtplib'):\n"
        "    assert mod not in sys.modules, f'{mod} leaked into GUI startup'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONNOUSERSITE="1", QT_QPA_PLATFORM="offscreen"),
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_qapplication_and_config_instantiation_avoids_nipype_and_scipy(tmp_path):
    """Verify that creating QApplication and initializing ConfigManager in a
    clean interpreter does not trigger nipype or scipy imports."""
    folder = str(tmp_path)
    code = (
        "import sys, os\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "import swane\n"
        "from swane.config.ConfigManager import ConfigManager\n"
        f"cfg = ConfigManager(global_base_folder={folder!r})\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication.instance() or QApplication(['swane'])\n"
        "from swane.ui.MainWindow import MainWindow\n"
        "assert 'nipype' not in sys.modules, f'Nipype leaked: {sys.modules.get(\"nipype\")}'\n"
        "assert 'scipy' not in sys.modules, f'SciPy leaked: {sys.modules.get(\"scipy\")}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONNOUSERSITE="1", QT_QPA_PLATFORM="offscreen"),
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_dependency_manager_instantiation_avoids_nipype():
    """Verify that instantiating DependencyManager does not load Nipype."""
    code = (
        "import sys\n"
        "from swane.utils.DependencyManager import DependencyManager\n"
        "dm = DependencyManager()\n"
        "assert 'nipype' not in sys.modules, f'Nipype leaked: {sys.modules.get(\"nipype\")}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONNOUSERSITE="1", QT_QPA_PLATFORM="offscreen"),
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
