"""Regression tests for ``MainWorkflow.launch_venous_ct_analysis`` non-contrast CT sink."""

import os
from unittest.mock import MagicMock

from nipype import Node
from nipype.interfaces.io import DataSink
from nipype.interfaces.utility import IdentityInterface

from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.utils.DataInputList import DataInputList as DIL
from swane.utils.SubjectInputStateList import (
    SubjectInputState,
    SubjectInputStateList,
)


def _build_main_for_venous_ct(tmp_path, monkeypatch, engine):
    subject_dir = tmp_path / "subject"
    dicom_dir = subject_dir / "dicom"
    for name in ("venous_ct", "venous_ct2"):
        (dicom_dir / name).mkdir(parents=True)

    slicer_exe = tmp_path / "Slicer"
    slicer_exe.write_text("")
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()

    global_config = ConfigManager(global_base_folder=str(tmp_path))
    global_config[GlobalPrefCategoryList.SYNTH]["engine"] = engine
    subject_config = ConfigManager(
        subject_folder=str(subject_dir), global_config=global_config
    )

    inputs = SubjectInputStateList(str(dicom_dir), global_config)
    for key in (DIL.VENOUS_CT, DIL.VENOUS_CT2, DIL.VENOUS_CT3, DIL.VENOUS_CT4):
        inputs.setdefault(key, SubjectInputState())
    inputs[DIL.VENOUS_CT].loaded = True
    inputs[DIL.VENOUS_CT].volumes = 1
    inputs[DIL.VENOUS_CT2].loaded = True
    inputs[DIL.VENOUS_CT2].volumes = 1

    monkeypatch.setattr(global_config, "get_slicer_path", lambda: str(slicer_exe))
    monkeypatch.setattr(
        global_config,
        "get_slicer_extensions_state",
        lambda: {"WrapSolidify": str(modules_dir)},
    )
    monkeypatch.setattr(
        "swane.nipype_pipeline.MainWorkflow.extension_module_dirs",
        lambda state, mods: [str(modules_dir)],
    )

    t1 = CustomWorkflow(name="ref", base_dir=str(subject_dir))
    t1_out = Node(
        IdentityInterface(fields=["reference", "reference_brain"]),
        name="outputnode",
    )
    t1.add_nodes([t1_out])

    main = CustomWorkflow.__new__(MainWorkflow)
    CustomWorkflow.__init__(main, name="test_main", base_dir=str(subject_dir))
    main.Result_DIR = "results"
    main.is_slicer = True
    main.max_cpu = 2
    main.test_run = False
    main.global_config = global_config
    main.subject_config = subject_config
    main.subject_input_state_list = inputs
    main.dependency_manager = MagicMock()
    main.t1 = t1
    main.add_nodes([t1])

    main.launch_venous_ct_analysis()
    return main


def test_venous_ct_sinks_noncontrast_ct_with_deterministic_filename(
    tmp_path, monkeypatch
):
    """Both veins and basal outputs are sunk, and basal is renamed to r-ct_noncontrast.nii.gz."""
    main = _build_main_for_venous_ct(tmp_path, monkeypatch, engine="ANTS")

    basal_sink = main.venous_ct.get_node("SaveResults_outputnode_basal")
    veins_sink = main.venous_ct.get_node("SaveResults_outputnode_veins")
    assert basal_sink is not None
    assert veins_sink is not None
    assert basal_sink.inputs.container == "results"

    outputnode = main.venous_ct.get_node("outputnode")
    edge = main.venous_ct._graph.get_edge_data(outputnode, basal_sink)
    assert edge is not None
    assert ("basal", "@file") in edge["connect"]

    sink_iface = DataSink()
    sink_iface.inputs.regexp_substitutions = basal_sink.inputs.regexp_substitutions
    # Verify both ANTS and FSL intermediate filenames resolve to the contract name.
    for sample_name in ("ants_reg_warped.nii.gz", "veins_reoriented_roi_flirt.nii.gz"):
        dest = os.path.join(str(tmp_path), "results", sample_name)
        assert sink_iface._substitute(dest) == os.path.join(
            str(tmp_path), "results", "r-ct_noncontrast.nii.gz"
        )
