"""Unit tests for :mod:`swane.utils.slicer_isolation`."""

import json

import pytest

from swane.utils.slicer_isolation import (
    ISOLATION_FLAGS,
    extension_module_dirs,
    isolation_args,
)


def _state(module_paths):
    return json.dumps({"revision": "1", "paths": {}, "module_paths": module_paths})


def test_extension_module_dirs_in_extension_order(tmp_path):
    dirs = {}
    for name in ("a", "b1", "b2"):
        (tmp_path / name).mkdir()
        dirs[name] = str(tmp_path / name)
    state = _state({"B": [dirs["b1"], dirs["b2"]], "A": [dirs["a"]]})
    assert extension_module_dirs(state, ["A", "B"]) == [
        dirs["a"],
        dirs["b1"],
        dirs["b2"],
    ]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json",
        "[]",
        json.dumps({"paths": {}}),  # recorded before the module folders were
        json.dumps({"module_paths": []}),
        _state({"A": []}),
        _state({"A": "not a list"}),
        _state({"A": [1]}),
        _state({"B": ["/x"]}),  # required extension missing
    ],
)
def test_extension_module_dirs_rejects_unusable_state(raw):
    assert extension_module_dirs(raw, ["A"]) is None


def test_extension_module_dirs_rejects_removed_folder(tmp_path):
    state = _state({"A": [str(tmp_path / "gone")]})
    assert extension_module_dirs(state, ["A"]) is None


def test_isolation_args():
    assert ISOLATION_FLAGS == ("--disable-settings", "--ignore-slicerrc")
    assert isolation_args(["/a", "/b c"]) == [
        "--disable-settings",
        "--ignore-slicerrc",
        "--additional-module-paths",
        "/a",
        "/b c",
    ]
    assert isolation_args([]) == ["--disable-settings", "--ignore-slicerrc"]
