"""
Real-Slicer regression tests for the IC timecourse viewer of
``workers/slicer_script_result.py``.

The viewer is installed once per Slicer session (by the slicerrc bootstrap)
and outlives every scene the user opens, so these tests drive it through scene
changes inside a real Slicer. They are heavy, opt-in tests (``--run-heavy``).
"""

import json
import os
import textwrap

import pytest

import swane
from swane.tests.helpers.slicer_runner import run_slicer_script

pytestmark = [
    pytest.mark.heavy,
    pytest.mark.requires_slicer,
    pytest.mark.requires_display,
]

WORKERS_DIR = os.path.join(os.path.dirname(swane.__file__), "workers")

# make_scene() builds what a SWANe resting-state scene gives the viewer: a mix
# table flagged with IC_MIX_TABLE_ATTRIBUTE and an IC zstat map, then shows the
# map in a slice view, which is what makes the viewer plot its timecourse.
# state() reports whether the viewer's chart and table belong to the current
# scene and what the plotted table holds.
DRIVER = textwrap.dedent("""
    import json
    import os
    import sys

    import numpy as np
    import slicer
    import vtk

    sys.path.insert(0, {workers_dir!r})
    import slicer_script_result as ssr

    out_json = {out_json!r}
    result = {{}}


    def make_scene(values):
        table = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "mix")
        table.SetAttribute(ssr.IC_MIX_TABLE_ATTRIBUTE, "1")
        column = vtk.vtkDoubleArray()
        column.SetName("IC1")
        for value in values:
            column.InsertNextValue(value)
        table.GetTable().AddColumn(column)
        volume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", "r-zstat1"
        )
        slicer.util.updateVolumeFromArray(
            volume, np.zeros((2, 2, 2), dtype=np.float32)
        )
        composites = slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode")
        composite = (
            composites[0]
            if composites
            else slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSliceCompositeNode")
        )
        composite.SetForegroundVolumeID(None)
        composite.SetForegroundVolumeID(volume.GetID())


    def state(viewer):
        chart = viewer._chart_node
        table = viewer._plot_table_node
        present = slicer.mrmlScene.IsNodePresent
        rows = table.GetTable().GetNumberOfRows() if table else 0
        return {{
            "chart_in_scene": bool(chart is not None and present(chart)),
            "table_in_scene": bool(table is not None and present(table)),
            "plotted": [
                table.GetTable().GetValueByName(i, "Timecourse").ToDouble()
                for i in range(rows)
            ],
        }}


    try:
        ssr.install_timecourse_viewer()
        viewer = slicer.swaneTimecourseViewer

        make_scene([1.0, 2.0, 3.0])
        result["scene_a"] = state(viewer)

        # File > Close Scene, then a new scene showing the same IC
        slicer.mrmlScene.Clear(0)
        make_scene([7.0, 8.0, 9.0])
        result["scene_b"] = state(viewer)

        # the user deletes the plot table by hand, in the same scene
        slicer.mrmlScene.RemoveNode(viewer._plot_table_node)
        composite = slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode")[0]
        composite.SetForegroundVolumeID(None)
        make_scene([4.0, 5.0, 6.0])
        result["table_deleted"] = state(viewer)
    except Exception:
        import traceback

        result["error"] = traceback.format_exc()
    with open(out_json, "w") as f:
        json.dump(result, f)
    sys.stdout.flush()
    os._exit(0)
    """)


def test_viewer_follows_scene_close_and_deleted_plot_nodes(slicer_executable, tmp_path):
    out_json = tmp_path / "viewer.json"
    driver = tmp_path / "viewer_driver.py"
    driver.write_text(DRIVER.format(workers_dir=WORKERS_DIR, out_json=str(out_json)))

    proc = run_slicer_script(slicer_executable, driver, timeout=300)

    assert out_json.exists(), proc.stdout + proc.stderr
    result = json.loads(out_json.read_text())
    assert "error" not in result, result.get("error")
    assert result["scene_a"] == {
        "chart_in_scene": True,
        "table_in_scene": True,
        "plotted": [1.0, 2.0, 3.0],
    }
    assert result["scene_b"] == {
        "chart_in_scene": True,
        "table_in_scene": True,
        "plotted": [7.0, 8.0, 9.0],
    }
    assert result["table_deleted"]["table_in_scene"] is True
    assert result["table_deleted"]["chart_in_scene"] is True
