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
    _normalise_conn_field,
    _normalise_function_source,
    _render_cmd,
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


def test_conn_field_normalises_embedded_transform_function():
    # nipype connections may carry an inline transform: (field, source, args).
    # A comment/formatting edit inside that source must not change the rendered
    # connection (same guarantee as node function_str traits).
    a = ("percentile_values", "def f(v):\n    # a comment\n    return v[0]\n", ())
    b = ("percentile_values", "def f(v):\n    return v[0]  # other comment\n", ())
    assert _normalise_conn_field(a, []) == _normalise_conn_field(b, [])
    # a logic change still shows
    c = ("percentile_values", "def f(v):\n    return v[1]\n", ())
    assert _normalise_conn_field(a, []) != _normalise_conn_field(c, [])
    # a plain (non-tuple) field name is returned unchanged
    assert _normalise_conn_field("percentile_values", []) == "percentile_values"


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


def test_render_cmd_windows_quoted_executable_matches_linux():
    """On Windows SWANe quotes an absolute executable path for cmd.exe
    (``windows_compat.shell_executable``), so the command is
    ``"C:\\...\\dcm2niix.exe"``. It must render exactly like the bare Linux
    path, otherwise every golden containing that command differs on Windows.
    """
    repl = build_replacements(tmp_root=os.getcwd())
    linux = _render_cmd("/opt/env/site-packages/dcm2niix/dcm2niix", repl)
    windows = _render_cmd(
        '"C:\\Users\\Name Surname\\env\\Lib\\site-packages\\dcm2niix\\dcm2niix.exe"',
        repl,
    )
    assert linux == "dcm2niix"
    assert windows == linux
    assert _render_cmd('"C:/env/niimath.exe"', repl) == "niimath"
    assert _render_cmd("niimath", repl) == "niimath"


def test_render_cmd_keeps_posix_double_quotes_visible():
    """Only Windows-looking executables are unquoted: a double-quoted POSIX
    command would be a quoting regression and must show up in the goldens."""
    repl = build_replacements(tmp_root=os.getcwd())
    assert _render_cmd('"/opt/env/dcm2niix/dcm2niix"', repl) == 'dcm2niix"'
    assert _render_cmd('"niimath"', repl) == '"niimath"'
