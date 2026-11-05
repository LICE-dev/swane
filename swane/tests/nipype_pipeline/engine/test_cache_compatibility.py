"""Tests for :mod:`swane.nipype_pipeline.engine.cache_compatibility`.

A workflow directory written by an older SWANe pickles its interface classes by
module path: once a module is moved (e.g. the 0.3 move of
``swane.nipype_pipeline.nodes.*`` to ``interfaces/<tool>/``) Nipype cannot load
those results and a resumed run aborts. The check must flag such a directory
without unpickling anything.
"""

import gzip
import pickle
import sys
import types

import pytest

from swane.nipype_pipeline.engine.cache_compatibility import (
    find_unloadable_result,
)

OLD_PACKAGE = "swane.nipype_pipeline.nodes"
OLD_MODULE = OLD_PACKAGE + ".CustomDcm2niix"


def _legacy_class(monkeypatch, module_name=OLD_MODULE, class_name="CustomDcm2niix"):
    """Register a temporary module holding a class, as an older SWANe had."""
    package_name = module_name.rsplit(".", 1)[0]
    if package_name not in sys.modules:
        monkeypatch.setitem(sys.modules, package_name, types.ModuleType(package_name))
    module = types.ModuleType(module_name)
    cls = type(class_name, (), {})
    cls.__module__ = module_name
    cls.__qualname__ = class_name
    setattr(module, class_name, cls)
    monkeypatch.setitem(sys.modules, module_name, module)
    return cls


def _write_result(path, record, protocol=pickle.DEFAULT_PROTOCOL, metadata=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = pickle.dumps(record, protocol=protocol)
    if metadata:
        content = b'{"version": "1.12.0"}\n' + content
    with gzip.open(path, "wb") as f:
        f.write(content)


def _record(interface):
    # Repeated strings make the pickler memoize and reuse them (BINGET), as in
    # a real result file.
    return {
        "interface": interface,
        "outputs": {"out_file": "/x/a.nii.gz", "other": "/x/a.nii.gz"},
        "runtime": [1, 2.5, None, "/x/a.nii.gz"],
    }


@pytest.mark.parametrize("protocol", [2, 4, pickle.HIGHEST_PROTOCOL])
def test_result_referencing_a_moved_module_is_flagged(tmp_path, monkeypatch, protocol):
    legacy = _legacy_class(monkeypatch)
    result = tmp_path / "wf" / "convert" / "result_convert.pklz"
    _write_result(result, _record(legacy()), protocol=protocol)
    # SWANe 0.3: the old module is gone
    monkeypatch.delitem(sys.modules, OLD_MODULE)
    monkeypatch.delitem(sys.modules, OLD_PACKAGE)

    assert find_unloadable_result(str(tmp_path / "wf")) == str(result)


@pytest.mark.parametrize("protocol", [2, 4, pickle.HIGHEST_PROTOCOL])
def test_result_referencing_current_classes_is_loadable(tmp_path, protocol):
    from swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix import (
        CustomDcm2niix,
    )

    _write_result(
        tmp_path / "wf" / "convert" / "result_convert.pklz",
        _record(CustomDcm2niix),
        protocol=protocol,
    )
    _write_result(
        tmp_path / "wf" / "sub" / "mapflow" / "_n0" / "result__n0.pklz",
        {"set": {1, 2}, "obj": types.SimpleNamespace(a="b")},
        protocol=protocol,
        metadata=True,
    )

    assert find_unloadable_result(str(tmp_path / "wf")) is None


def test_class_missing_from_an_existing_module_is_flagged(tmp_path, monkeypatch):
    module_name = "swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix"
    legacy = type("RemovedInterface", (), {})
    legacy.__module__ = module_name
    legacy.__qualname__ = "RemovedInterface"
    import swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix as module

    monkeypatch.setattr(module, "RemovedInterface", legacy, raising=False)
    result = tmp_path / "wf" / "n" / "result_n.pklz"
    _write_result(result, _record(legacy()))
    monkeypatch.delattr(module, "RemovedInterface")

    assert find_unloadable_result(str(tmp_path / "wf")) == str(result)


def test_unreadable_result_is_flagged(tmp_path):
    result = tmp_path / "wf" / "n" / "result_n.pklz"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"not a gzip pickle")

    assert find_unloadable_result(str(tmp_path / "wf")) == str(result)


def test_directory_without_results_is_loadable(tmp_path):
    (tmp_path / "wf" / "n").mkdir(parents=True)
    (tmp_path / "wf" / "n" / "_inputs.pklz").write_bytes(b"ignored")

    assert find_unloadable_result(str(tmp_path / "wf")) is None
    assert find_unloadable_result(str(tmp_path / "missing")) is None


def test_check_never_unpickles(tmp_path, monkeypatch):
    from swane.nipype_pipeline.interfaces.dcm2nii.CustomDcm2niix import (
        CustomDcm2niix,
    )

    _write_result(tmp_path / "wf" / "n" / "result_n.pklz", _record(CustomDcm2niix))

    def _fail(*args, **kwargs):
        raise AssertionError("the check must not unpickle")

    monkeypatch.setattr(pickle, "loads", _fail)
    monkeypatch.setattr(pickle, "load", _fail)
    monkeypatch.setattr(pickle, "Unpickler", _fail)

    assert find_unloadable_result(str(tmp_path / "wf")) is None


def test_real_nipype_result_of_a_moved_interface_is_flagged(tmp_path, monkeypatch):
    """A result file written by Nipype itself, whose interface module is then
    moved, is flagged; the same file with the module in place is not."""
    from nipype import Node, Workflow
    from nipype.interfaces.base import (
        BaseInterface,
        BaseInterfaceInputSpec,
        TraitedSpec,
        traits,
    )

    module_name = "swane_test_legacy_nodes.Touch"
    monkeypatch.setitem(
        sys.modules,
        "swane_test_legacy_nodes",
        types.ModuleType("swane_test_legacy_nodes"),
    )
    module = types.ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)

    class TouchInputSpec(BaseInterfaceInputSpec):
        value = traits.Int(mandatory=True)

    class TouchOutputSpec(TraitedSpec):
        out = traits.Int()

    class Touch(BaseInterface):
        input_spec = TouchInputSpec
        output_spec = TouchOutputSpec

        def _run_interface(self, runtime):
            return runtime

        def _list_outputs(self):
            return {"out": self.inputs.value + 1}

    for cls in (TouchInputSpec, TouchOutputSpec, Touch):
        cls.__module__ = module_name
        cls.__qualname__ = cls.__name__
        setattr(module, cls.__name__, cls)

    workflow = Workflow(name="wf", base_dir=str(tmp_path))
    first = Node(Touch(value=1), name="convert")
    second = Node(Touch(), name="next")
    workflow.connect(first, "out", second, "value")
    workflow.run()

    assert find_unloadable_result(str(tmp_path / "wf")) is None

    monkeypatch.delitem(sys.modules, module_name)
    flagged = find_unloadable_result(str(tmp_path / "wf"))
    assert flagged is not None and flagged.endswith(".pklz")
