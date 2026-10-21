"""
Real-Slicer regression tests for ``workers/slicer_seg_endocranium.py``.

The script runs inside 3D Slicer's own Python, so every test here launches the
installed Slicer the way the ``SegmentEndocranium`` node does
(``--no-splash --no-main-window --python-script``) on synthetic volumes built
in ``tmp_path``. They are heavy, opt-in tests (``--run-heavy``).
"""

import json
import os
import subprocess
import textwrap

import numpy as np
import pytest

import swane

pytestmark = [
    pytest.mark.heavy,
    pytest.mark.requires_slicer,
    pytest.mark.requires_display,
]

WORKERS_DIR = os.path.join(os.path.dirname(swane.__file__), "workers")
SCRIPT_PATH = os.path.join(WORKERS_DIR, "slicer_seg_endocranium.py")


def _run_slicer(slicer_cmd, script, args=(), timeout=600):
    # conftest forces QT_QPA_PLATFORM=offscreen for swane's own Qt app;
    # Slicer's bundled Qt has no such plugin and would refuse to start.
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    return subprocess.run(
        [
            slicer_cmd,
            "--no-splash",
            "--no-main-window",
            "--python-script",
            str(script),
            *map(str, args),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# The driver builds a bone block on a 1 x 1 x 2 mm grid crossed by two gaps
# that are both 2 mm wide: one 2 voxels wide along x, one 1 voxel wide along z.
# A closing kernel in mm sizes itself per axis from the spacing (3 mm -> 3 x 3
# x 1 voxels, 5 mm -> 5 x 5 x 3 voxels), so 3 mm can fill the x gap but not
# the z gap, while 5 mm fills both. A kernel read in voxels would fill the z
# gap at 3 already.
CLOSING_DRIVER = textwrap.dedent("""
    import json
    import os
    import sys

    import numpy as np
    import slicer

    sys.path.insert(0, {workers_dir!r})
    import slicer_seg_endocranium as seg

    out_json = {out_json!r}
    result = {{}}
    try:
        arr = np.zeros((20, 40, 40), dtype=np.int16)  # k (z), j (y), i (x)
        arr[3:17, 5:35, 5:35] = 1
        arr[:, :, 19:21] = 0  # 2 mm gap along x (2 voxels)
        arr[10, :, :] = 0  # 2 mm gap along z (1 voxel)

        for kernel in (3.0, 5.0):
            slicer.mrmlScene.Clear(0)
            volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
            slicer.util.updateVolumeFromArray(volume, arr)
            volume.SetSpacing(1.0, 1.0, 2.0)

            segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode"
            )
            segmentationNode.CreateDefaultDisplayNodes()
            segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(volume)
            segmentation = segmentationNode.GetSegmentation()

            editorWidget = slicer.qMRMLSegmentEditorWidget()
            editorWidget.setMRMLScene(slicer.mrmlScene)
            editorNode = slicer.vtkMRMLSegmentEditorNode()
            slicer.mrmlScene.AddNode(editorNode)
            editorWidget.setMRMLSegmentEditorNode(editorNode)
            editorWidget.setSegmentationNode(segmentationNode)
            editorWidget.setSourceVolumeNode(volume)

            rawID = segmentation.AddEmptySegment("raw")
            editorNode.SetSelectedSegmentID(rawID)
            editorWidget.setActiveEffectByName("Threshold")
            effect = editorWidget.activeEffect()
            effect.setParameter("MinimumThreshold", "1")
            effect.setParameter("MaximumThreshold", "1")
            effect.self().onApply()

            smoothID = segmentation.AddEmptySegment("smooth")
            segmentation.GetSegment(smoothID).DeepCopy(segmentation.GetSegment(rawID))

            seg.smooth_segment_morphological_closing(
                segmentEditorWidget=editorWidget,
                segmentEditorNode=editorNode,
                segmentId=smoothID,
                kernelSizeMm=kernel,
            )

            def segment_array(segmentId):
                labelmap = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLLabelMapVolumeNode"
                )
                slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
                    segmentationNode, [segmentId], labelmap, volume
                )
                return slicer.util.arrayFromVolume(labelmap) != 0

            raw = segment_array(rawID)
            smooth = segment_array(smoothID)
            x_gap = smooth[5:9, 8:32, 19:21]
            z_gap = smooth[10, 8:32, 8:18]
            result[str(kernel)] = {{
                "raw_unchanged": bool(np.array_equal(raw, arr != 0)),
                "smooth_contains_raw": bool(np.all(smooth[raw])),
                "x_gap_closed": bool(np.all(x_gap)),
                "z_gap_closed": bool(np.all(z_gap)),
            }}
    except Exception:
        import traceback

        result["error"] = traceback.format_exc()
    with open(out_json, "w") as f:
        json.dump(result, f)
    sys.stdout.flush()
    os._exit(0)
    """)


def test_closing_kernel_is_in_mm_and_fills_the_smoothed_segment(
    slicer_executable, tmp_path
):
    out_json = tmp_path / "closing.json"
    driver = tmp_path / "closing_driver.py"
    driver.write_text(
        CLOSING_DRIVER.format(workers_dir=WORKERS_DIR, out_json=str(out_json))
    )

    proc = _run_slicer(slicer_executable, driver)

    assert out_json.exists(), proc.stdout + proc.stderr
    result = json.loads(out_json.read_text())
    assert "error" not in result, result.get("error")
    for kernel in ("3.0", "5.0"):
        # the closing only adds voxels to the smoothed copy and leaves the
        # source segment alone
        assert result[kernel]["raw_unchanged"], result
        assert result[kernel]["smooth_contains_raw"], result
    assert result["3.0"]["x_gap_closed"], result
    assert not result["3.0"]["z_gap_closed"], result
    assert result["5.0"]["x_gap_closed"], result
    assert result["5.0"]["z_gap_closed"], result


def _write_ct_phantom(path):
    """Write a small synthetic head CT: an ellipsoidal skull shell (1500 HU)
    around a brain (35 HU), cut by two 2 mm slots, on a 1 x 1 x 2 mm grid."""
    import nibabel as nib

    spacing = np.array([1.0, 1.0, 2.0])
    shape = (100, 116, 60)
    idx = np.indices(shape).astype(float)
    center = (np.array(shape) - 1) / 2
    x, y, z = [(idx[i] - center[i]) * spacing[i] for i in range(3)]
    r = np.sqrt((x / 40) ** 2 + (y / 48) ** 2 + (z / 46) ** 2)
    img = np.full(shape, -1000.0)
    img[r < 1.12] = 40.0
    skull = (r >= 0.9) & (r < 1.05)
    img[skull] = 1500.0
    img[r < 0.9] = 35.0
    img[skull & (np.abs(x) < 1.0) & (y > 0)] = 40.0
    img[skull & (np.abs(y + 15) < 1.0) & (x > 0)] = 40.0
    affine = np.diag(list(spacing) + [1.0])
    affine[:3, 3] = -center * spacing
    nib.save(nib.Nifti1Image(img.astype(np.int16), affine), str(path))


def test_kernel_size_changes_the_endocranium_mask(slicer_executable, tmp_path):
    import nibabel as nib

    ct = tmp_path / "ct.nii.gz"
    _write_ct_phantom(ct)

    masks = {}
    for kernel in ("1", "6"):
        out = tmp_path / f"inskull_k{kernel}.nii.gz"
        proc = _run_slicer(
            slicer_executable,
            SCRIPT_PATH,
            [
                "--input",
                ct,
                "--output",
                out,
                "--kernel-mm",
                kernel,
                "--iterations",
                "2",
                "--oversampling",
                "1",
                "--skull_threshold",
                "500",
            ],
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert out.exists(), proc.stdout + proc.stderr
        masks[kernel] = np.asarray(nib.load(str(out)).dataobj) != 0

    assert masks["1"].any() and masks["6"].any()
    assert not np.array_equal(masks["1"], masks["6"])
