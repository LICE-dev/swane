import os
import subprocess
import sys


def test_gui_utilities_do_not_import_nipype():
    code = (
        "import sys\n"
        "from swane.utils.Subject import Subject\n"
        "from swane.utils.DependencyManager import DependencyManager\n"
        "from swane.utils.ResourceManager import ResourceManager\n"
        "assert 'nipype' not in sys.modules, f'Nipype was imported by utilities: {list(sys.modules.keys())}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONNOUSERSITE="1"),
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_subject_tab_does_not_import_nipype():
    code = (
        "import sys\n"
        "from swane.ui.SubjectTab import SubjectTab\n"
        "assert 'nipype' not in sys.modules, f'Nipype was imported by SubjectTab: {list(sys.modules.keys())}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONNOUSERSITE="1", QT_QPA_PLATFORM="offscreen"),
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_swane_package_import_does_not_import_nipype():
    code = (
        "import sys\n"
        "import swane\n"
        "assert 'nipype' not in sys.modules, f'Nipype imported by swane.__init__: {list(sys.modules.keys())}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONNOUSERSITE="1"),
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
