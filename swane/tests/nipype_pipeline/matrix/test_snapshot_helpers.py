"""Unit tests for the snapshot rendering helpers.

These pin the guarantee that :func:`_normalise_function_source` makes a
``Function`` node's captured source insensitive to comments and incidental
formatting, while still reflecting any change in the function's actual logic.
Without that guarantee, editing a comment inside a ``Function`` body would
spuriously fail the settings-matrix snapshot regression (nipype serialises the
full source, comments included, into the ``function_str`` input).
"""

import os
import site

from swane.tests.nipype_pipeline.matrix._snapshot import (
    _normalise,
    _normalise_function_source,
    build_replacements,
)


def test_ignores_comments():
    a = "def f(x):\n    # a comment\n    return x + 1\n"
    b = "def f(x):\n    return x + 1  # a different comment\n"
    assert _normalise_function_source(a) == _normalise_function_source(b)


def test_ignores_incidental_whitespace():
    a = "def f(x):\n    import os\n\n    return os.path.abspath(x)\n"
    b = "def f(x):\n    import os\n    return os.path.abspath(x)\n"
    assert _normalise_function_source(a) == _normalise_function_source(b)


def test_detects_logic_change():
    a = "def f(x):\n    return x + 1\n"
    b = "def f(x):\n    return x + 2\n"
    assert _normalise_function_source(a) != _normalise_function_source(b)


def test_unparseable_source_falls_back_to_input():
    garbage = "def f(:\n    not valid python\n"
    assert _normalise_function_source(garbage) == garbage


def test_user_site_packages_is_tokenised():
    """A path into an installed package must collapse to <SITE> whether the
    package sits in system site-packages, a virtualenv, or a `pip --user`
    user-site. Regression: only ``sysconfig purelib`` was tokenised, so a
    user-site path (e.g. ica_aroma_py resources under
    ~/.local/lib/pythonX.Y/site-packages) leaked into the golden and tied it to
    one developer's machine and Python version.
    """
    repl = build_replacements(tmp_root=os.getcwd())
    user_site = site.getusersitepackages().replace("\\", "/").rstrip("/")
    leaked = user_site + "/ica_aroma_py/resources/mask_csf.nii.gz"
    assert _normalise(leaked, repl) == "<SITE>/ica_aroma_py/resources/mask_csf.nii.gz"


def test_system_site_packages_is_tokenised():
    """Same guarantee for the interpreter's own site-packages root."""
    import sysconfig

    repl = build_replacements(tmp_root=os.getcwd())
    purelib = sysconfig.get_paths()["purelib"].replace("\\", "/").rstrip("/")
    leaked = purelib + "/dcm2niix/resources/x.nii.gz"
    assert _normalise(leaked, repl) == "<SITE>/dcm2niix/resources/x.nii.gz"
