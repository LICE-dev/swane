"""Portable Local Environment actions for the SWANe repository."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run(*arguments):
    subprocess.run(
        [str(argument) for argument in arguments], cwd=PROJECT_ROOT, check=True
    )


def run_python(*arguments):
    run(sys.executable, *arguments)


def assert_supported_python():
    if sys.version_info < (3, 12):
        raise SystemExit("SWANe development requires Python 3.12 or newer.")


def find_sibling(repository_name, marker):
    source_tree = Path(os.environ.get("CODEX_SOURCE_TREE_PATH", PROJECT_ROOT)).resolve()
    candidate = source_tree.parent / repository_name
    return candidate if (candidate / marker).is_file() else None


def bootstrap():
    run_python("-m", "pip", "install", "--upgrade", "pip")
    for repository_name, marker in (
        ("dicom_sequence_classifier", "dicom_sequence_classifier/__init__.py"),
    ):
        sibling = find_sibling(repository_name, marker)
        if sibling is not None:
            print("Installing sibling checkout: {0}".format(sibling))
            run_python("-m", "pip", "install", "-e", sibling)
    run_python(
        "-m",
        "pip",
        "install",
        "-e",
        ".",
        "pytest",
        "pytest-qt",
        "pytest-timeout",
        "SimpleITK",
        "black",
    )


def assert_safe_test_root():
    home = Path.home().resolve()
    test_root = (home / "test_swane").resolve()
    if test_root.parent != home or test_root.name != "test_swane":
        raise SystemExit("Unsafe SWANe test root: {0}".format(test_root))
    print("Tests may recreate task-specific directories below {0}".format(test_root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "setup",
            "bootstrap",
            "run",
            "compile",
            "core-tests",
            "workflow-tests",
            "format",
            "pip-check",
        ),
    )
    action = parser.parse_args().action
    assert_supported_python()

    if action == "setup":
        print(
            "Virtual environment ready. Run 'Bootstrap Python' to install dependencies."
        )
    elif action == "bootstrap":
        bootstrap()
    elif action == "run":
        run_python("-m", "swane")
    elif action == "compile":
        run_python("-m", "compileall", "swane")
    elif action == "core-tests":
        assert_safe_test_root()
        run_python(
            "-m",
            "pytest",
            "swane/tests",
            "-m",
            "not heavy",
            "--color=yes",
            "--verbose",
        )
    elif action == "workflow-tests":
        assert_safe_test_root()
        run_python(
            "-m",
            "pytest",
            "swane/tests/nipype_pipeline/matrix",
            "--color=yes",
            "--verbose",
        )
    elif action == "format":
        run_python("-m", "black", "--check", "swane")
    elif action == "pip-check":
        run_python("-m", "pip", "check")


if __name__ == "__main__":
    main()
