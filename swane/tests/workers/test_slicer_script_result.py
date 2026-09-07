"""
Regression tests for ``workers/slicer_script_result.py`` tract loading.

``slicer_script_result`` runs inside 3D Slicer's own Python and imports
``slicer``/``vtk``/``qt`` at module level, so these tests inject recording
stand-ins for those three modules and load the script as a standalone module.
Every call the script makes on them is appended to a log, and that log is what
the assertions below compare: the FSL ``.nii.gz`` result path is a stable
contract, so its Slicer call sequence is snapshotted exactly.
"""

import importlib.util
import os
import sys
import types

import pytest

import swane

MODULE_PATH = os.path.join(
    os.path.dirname(swane.__file__), "workers", "slicer_script_result.py"
)


class CallSpy:
    """
    Attribute/callable recorder standing in for a Slicer object.

    Every attribute access returns a child spy (memoised, so repeated access
    yields the same object and hence the same ``repr``), and every call appends
    ``"<path>(<args>)"`` to the shared log.
    """

    def __init__(self, path, log):
        self._path = path
        self._log = log
        self._children = {}

    def _child(self, key, path):
        if key not in self._children:
            self._children[key] = CallSpy(path, self._log)
        return self._children[key]

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self._child(name, f"{self._path}.{name}")

    def __call__(self, *args, **kwargs):
        rendered = [repr(a) for a in args]
        rendered += [f"{k}={v!r}" for k, v in kwargs.items()]
        self._log.append(f"{self._path}({', '.join(rendered)})")
        return self._child("()", f"{self._path}()")

    def __repr__(self):
        return f"<{self._path}>"


def _fake_module(name, log):
    module = types.ModuleType(name)
    root = CallSpy(name, log)
    module.__getattr__ = lambda attr, _root=root: getattr(_root, attr)
    return module


@pytest.fixture
def slicer_script(monkeypatch):
    """Load ``slicer_script_result`` with recording slicer/vtk/qt modules."""
    log = []
    for name in ("slicer", "vtk", "qt"):
        monkeypatch.setitem(sys.modules, name, _fake_module(name, log))

    spec = importlib.util.spec_from_file_location(
        "swane_slicer_script_result_under_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, log


def normalise(log, **paths):
    """Replace absolute fixture paths with stable tokens for snapshotting."""
    out = []
    for line in log:
        for token, path in paths.items():
            line = line.replace(str(path), f"<{token}>")
        out.append(line)
    return out


CST = {"name": "cst", "thr": 500, "color": [0, 1, 0]}
AF = {"name": "af", "thr": 1500, "color": [1, 0, 1]}
OR = {"name": "or", "thr": 500, "color": [1, 1, 0]}
TRACTS = [CST, AF, OR]

EDITOR = "slicer.qMRMLSegmentEditorWidget()"


def threshold_calls(seg, tract, tract_file, threshold):
    """
    The exact Slicer call sequence the ``.nii.gz`` (FSL) path produces for one
    tract, as recorded today. ``seg`` is the ``repr`` path of the segmentation
    node spy.
    """
    name = tract["name"]
    return [
        f"slicer.util.loadVolume('{tract_file}')",
        f"{seg}.SetReferenceImageGeometryParameterFromVolumeNode"
        f"(<slicer.util.loadVolume()>)",
        f"{EDITOR}",
        f"{EDITOR}.setMRMLScene(<slicer.mrmlScene>)",
        "slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentEditorNode')",
        f"{EDITOR}.setMRMLSegmentEditorNode(<slicer.mrmlScene.AddNewNodeByClass()>)",
        f"{EDITOR}.setSegmentationNode(<{seg}>)",
        f"{EDITOR}.setSourceVolumeNode(<slicer.util.loadVolume()>)",
        f"{seg}.GetSegmentation()",
        f"{seg}.GetSegmentation().AddEmptySegment"
        f"({name!r}, {name!r}, {tract['color']!r})",
        "slicer.mrmlScene.AddNewNodeByClass().SetSelectedSegmentID"
        f"(<{seg}.GetSegmentation().AddEmptySegment()>)",
        f"{EDITOR}.setActiveEffectByName('Threshold')",
        f"{EDITOR}.activeEffect()",
        f"{EDITOR}.activeEffect().setParameter('MinimumThreshold', {threshold!r})",
        f"{EDITOR}.activeEffect().self()",
        f"{EDITOR}.activeEffect().self().onApply()",
        f"{EDITOR}.setActiveEffect(None)",
        f"{EDITOR}.setSegmentationNode(None)",
        f"{EDITOR}.setSourceVolumeNode(None)",
        "slicer.mrmlScene.RemoveNode(<slicer.mrmlScene.AddNewNodeByClass()>)",
        f"{EDITOR}.deleteLater()",
        "slicer.mrmlScene.RemoveNode(<slicer.util.loadVolume()>)",
    ]


class TestNiftiPathUnchanged:
    """
    The FSL ``.nii.gz`` result path is a contract: waytotal-driven adaptive
    thresholding through the Segment Editor, one segment per tract, one
    ``tracts_<side>.seg.nrrd`` per hemisphere. It must not move.
    """

    def test_tract_model_call_sequence_with_waytotal(
        self, slicer_script, tmp_path, capsys
    ):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()
        (dti_dir / "r-cst_lh.nii.gz").write_bytes(b"")
        (dti_dir / "r-cst_lh_waytotal").write_text("200000\n")

        node = CallSpy("segmentation_node", log)
        module.tract_model(
            segmentation_node=node, dti_dir=str(dti_dir), tract=CST, side="lh"
        )

        # 200000 * 0.0035 = 700.0, the adaptive threshold.
        assert normalise(log, dti=dti_dir) == threshold_calls(
            "segmentation_node", CST, "<dti>/r-cst_lh.nii.gz", 700.0
        )
        assert "threshold=700.00" in capsys.readouterr().out

    def test_threshold_falls_back_to_tract_default_without_waytotal(
        self, slicer_script, tmp_path
    ):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()
        (dti_dir / "r-cst_lh.nii.gz").write_bytes(b"")

        node = CallSpy("segmentation_node", log)
        module.tract_model(
            segmentation_node=node, dti_dir=str(dti_dir), tract=CST, side="lh"
        )

        assert f"{EDITOR}.activeEffect().setParameter('MinimumThreshold', 500.0)" in log

    def test_missing_tract_file_makes_no_slicer_calls(self, slicer_script, tmp_path):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()

        node = CallSpy("segmentation_node", log)
        module.tract_model(
            segmentation_node=node, dti_dir=str(dti_dir), tract=CST, side="lh"
        )

        assert log == []

    def test_main_tract_call_sequence(self, slicer_script, tmp_path):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        for side in ("rh", "lh"):
            for tract in TRACTS:
                (dti_dir / f"r-{tract['name']}_{side}.nii.gz").write_bytes(b"")
        (dti_dir / "r-af_lh_waytotal").write_text("400000\n")

        module.main_tract(str(dti_dir), str(scene_dir))

        # Inside main_tract the segmentation node and the segment editor node
        # are both created through AddNewNodeByClass, so they share a repr.
        seg = "slicer.mrmlScene.AddNewNodeByClass()"
        expected = []
        for side in ("rh", "lh"):
            expected.append(
                "slicer.mrmlScene.AddNewNodeByClass"
                f"('vtkMRMLSegmentationNode', 'tracts_{side}')"
            )
            expected.append(f"{seg}.CreateDefaultDisplayNodes()")
            for tract in TRACTS:
                # 400000 * 0.0035 = 1400.0 for af_lh; every other tract falls
                # back to its own default threshold.
                threshold = (
                    1400.0 if (tract is AF and side == "lh") else float(tract["thr"])
                )
                expected += threshold_calls(
                    seg,
                    tract,
                    f"<dti>/r-{tract['name']}_{side}.nii.gz",
                    threshold,
                )
            expected.append(f"{seg}.CreateClosedSurfaceRepresentation()")
            expected.append(f"{seg}.CreateDefaultStorageNode()")
            expected.append(
                f"{seg}.CreateDefaultStorageNode().SetFileName"
                f"('<scene>/tracts_{side}.seg.nrrd')"
            )
            expected.append(f"{seg}.CreateDefaultStorageNode().WriteData(<{seg}>)")

        assert normalise(log, dti=dti_dir, scene=scene_dir) == expected

    def test_main_tract_ignores_a_missing_dti_dir(self, slicer_script, tmp_path):
        module, log = slicer_script

        module.main_tract(str(tmp_path / "nope"), str(tmp_path))

        assert log == []


def bundle_calls(tract, side, bundle_file):
    """
    The Slicer call sequence for one dipy bundle: a plain model load, no
    thresholding. The ``.vtp`` is written in the reference space, so it is
    loaded as-is, with no transform applied.
    """
    model = "slicer.util.loadModel()"
    color = ", ".join(repr(c) for c in tract["color"])
    return [
        f"slicer.util.loadModel('{bundle_file}')",
        f"{model}.SetName('{tract['name']}_{side}')",
        f"{model}.CreateDefaultDisplayNodes()",
        f"{model}.GetDisplayNode()",
        f"{model}.GetDisplayNode().SetColor({color})",
        f"{model}.GetDisplayNode().SetVisibility2D(True)",
    ]


class TestVtpBundleBranch:
    """
    The dipy engine writes ``r-<tract>_<side>.vtp`` (VTK PolyData, in the
    reference space, natively readable by Slicer). Those load as fiber-bundle
    models, with no thresholding and no waytotal.
    """

    def test_bundle_is_loaded_as_a_model_without_thresholding(
        self, slicer_script, tmp_path
    ):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        for side in ("rh", "lh"):
            for tract in TRACTS:
                (dti_dir / f"r-{tract['name']}_{side}.vtp").write_bytes(b"")

        module.main_tract(str(dti_dir), str(scene_dir))

        expected = []
        for side in ("rh", "lh"):
            for tract in TRACTS:
                expected += bundle_calls(
                    tract, side, f"<dti>/r-{tract['name']}_{side}.vtp"
                )
        assert normalise(log, dti=dti_dir, scene=scene_dir) == expected
        # No segmentation, no thresholding, no volume load, no .seg.nrrd.
        assert not list(scene_dir.iterdir())

    def test_nifti_and_waytotal_are_ignored_when_a_vtp_is_present(
        self, slicer_script, tmp_path, monkeypatch
    ):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()
        (dti_dir / "r-cst_lh.vtp").write_bytes(b"")
        (dti_dir / "r-cst_lh.nii.gz").write_bytes(b"")
        (dti_dir / "r-cst_lh_waytotal").write_text("200000\n")

        opened = []
        real_open = open

        def recording_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        import builtins

        monkeypatch.setattr(builtins, "open", recording_open)

        module.tract_bundle(dti_dir=str(dti_dir), tract=CST, side="lh")

        assert normalise(log, dti=dti_dir) == bundle_calls(
            CST, "lh", "<dti>/r-cst_lh.vtp"
        )
        assert opened == []

    def test_missing_bundle_file_makes_no_slicer_calls(self, slicer_script, tmp_path):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()

        module.tract_bundle(dti_dir=str(dti_dir), tract=CST, side="lh")

        assert log == []

    def test_a_vtp_tract_does_not_disturb_the_nifti_tracts_on_the_same_side(
        self, slicer_script, tmp_path
    ):
        module, log = slicer_script
        dti_dir = tmp_path / "dti"
        dti_dir.mkdir()
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        (dti_dir / "r-cst_lh.vtp").write_bytes(b"")
        for tract in (AF, OR):
            (dti_dir / f"r-{tract['name']}_lh.nii.gz").write_bytes(b"")

        module.main_tract(str(dti_dir), str(scene_dir))

        seg = "slicer.mrmlScene.AddNewNodeByClass()"
        expected = bundle_calls(CST, "lh", "<dti>/r-cst_lh.vtp")
        expected.append(
            "slicer.mrmlScene.AddNewNodeByClass"
            "('vtkMRMLSegmentationNode', 'tracts_lh')"
        )
        expected.append(f"{seg}.CreateDefaultDisplayNodes()")
        for tract in (AF, OR):
            expected += threshold_calls(
                seg,
                tract,
                f"<dti>/r-{tract['name']}_lh.nii.gz",
                float(tract["thr"]),
            )
        expected.append(f"{seg}.CreateClosedSurfaceRepresentation()")
        expected.append(f"{seg}.CreateDefaultStorageNode()")
        expected.append(
            f"{seg}.CreateDefaultStorageNode().SetFileName"
            "('<scene>/tracts_lh.seg.nrrd')"
        )
        expected.append(f"{seg}.CreateDefaultStorageNode().WriteData(<{seg}>)")

        # The rh side has no file at all, so it keeps producing its (empty)
        # segmentation exactly as today.
        expected = [
            "slicer.mrmlScene.AddNewNodeByClass"
            "('vtkMRMLSegmentationNode', 'tracts_rh')",
            f"{seg}.CreateDefaultDisplayNodes()",
            f"{seg}.CreateClosedSurfaceRepresentation()",
            f"{seg}.CreateDefaultStorageNode()",
            f"{seg}.CreateDefaultStorageNode().SetFileName"
            "('<scene>/tracts_rh.seg.nrrd')",
            f"{seg}.CreateDefaultStorageNode().WriteData(<{seg}>)",
        ] + expected

        assert normalise(log, dti=dti_dir, scene=scene_dir) == expected
