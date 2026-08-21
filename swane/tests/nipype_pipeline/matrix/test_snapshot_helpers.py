"""Unit tests for the snapshot rendering helpers.

These pin the guarantee that :func:`_normalise_function_source` makes a
``Function`` node's captured source insensitive to comments and incidental
formatting, while still reflecting any change in the function's actual logic.
Without that guarantee, editing a comment inside a ``Function`` body would
spuriously fail the settings-matrix snapshot regression (nipype serialises the
full source, comments included, into the ``function_str`` input).
"""

from swane.tests.nipype_pipeline.matrix._snapshot import _normalise_function_source


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
