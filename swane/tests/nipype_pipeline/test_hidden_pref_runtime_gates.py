"""Subject booleans the preferences window hides keep their stored value.

``PreferencesWindow`` hides (instead of graying out and unchecking) a subject
boolean whose requirement cannot be met from that window: a requirement on a
global preference (e.g. the Synth-tools engines) or an input series that is
not loaded. The stored value, possibly ``true``, is kept, so every runtime
consumer must re-check the gate itself. These tests build the real
MainWorkflow with each such boolean ``true`` and its gate unmet (no node), and
met (node built, so the node lookup is proven to work).
"""

import pytest

from swane.config import dependency_policy
from swane.config.ConfigManager import ConfigManager
from swane.config.PreferenceEntry import InputTypes
from swane.config.config_enums import (
    DeskullEngine,
    GlobalPrefCategoryList,
    TractographyEngine,
)
from swane.config.preference_list import (
    DEFAULT_N_SAMPLES,
    TRACTS,
    WF_PREFERENCES,
    tract_preference_entry,
)
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
from swane.nipype_pipeline.workflows import tractography_workflow
from swane.nipype_pipeline.workflows.workflow_constants import DIPY_TRACT_ATLAS
from swane.utils.DataInputList import DataInputList as DIL
from swane.utils.DependencyManager import DependencyManager
from swane.utils.SubjectInputStateList import SubjectInputStateList

# Every subject boolean hidden by an unmet global or input requirement, and
# the test below proving its consumer re-checks the gate.
HIDDEN_GATED_BOOLEANS = {
    (DIL.T13D, "bet_bias_correction"): "test_bet_bias_correction",
    (DIL.FLAIR3D, "bet_bias_correction"): "test_bet_bias_correction",
    (DIL.MDC, "bet_bias_correction"): "test_bet_bias_correction",
    (DIL.T13D, "flat1"): "test_flat1",
    (DIL.DTI, "old_eddy_correct"): "test_old_eddy_correct",
    (DIL.DTI, "cingulum"): "test_cingulum",
}
# The FSL-only tracts exist only where the XTRACT data is installed
HIDDEN_GATED_BOOLEANS.update(
    {
        (DIL.DTI, tract): "test_fsl_only_tract"
        for tract in TRACTS
        if tract not in DIPY_TRACT_ATLAS
    }
)


def test_every_hidden_gated_boolean_has_a_runtime_gate_test():
    """A new subject boolean with a global or input requirement must get a
    runtime gate test here: the preferences window no longer turns it off."""
    found = set()
    for category, entries in WF_PREFERENCES.items():
        for key, entry in entries.items():
            if entry.input_type != InputTypes.BOOLEAN:
                continue
            global_requirement = any(
                isinstance(req_category, GlobalPrefCategoryList)
                for req_category in (entry.pref_requirement or {})
            )
            if global_requirement or entry.input_requirement:
                found.add((category, key))
    assert found == set(HIDDEN_GATED_BOOLEANS)
    assert all(name in globals() for name in HIDDEN_GATED_BOOLEANS.values())


@pytest.fixture
def build(tmp_path, isolated_home, monkeypatch):
    """Build the whole MainWorkflow with every input loaded but the given ones;
    only constructs the graph, no tool runs."""
    monkeypatch.setattr(DependencyManager, "is_fsl", lambda self=None: True)
    monkeypatch.setenv("SUBJECTS_DIR", str(tmp_path))

    def _build(synth, subject, unloaded=()):
        subject_dir = tmp_path / ("subject_%d" % len(list(tmp_path.iterdir())))
        dicom_dir = subject_dir / "dicom"
        dicom_dir.mkdir(parents=True)
        global_dir = subject_dir / "global"
        global_dir.mkdir()
        global_config = ConfigManager(global_base_folder=str(global_dir))
        global_config.set_main_working_directory(str(tmp_path))
        for key, engine in dependency_policy.default_engines(False).items():
            global_config[GlobalPrefCategoryList.SYNTH][key] = engine.name
        for key, value in synth.items():
            global_config[GlobalPrefCategoryList.SYNTH][key] = value
        subject_config = ConfigManager(
            subject_folder=str(subject_dir), global_config=global_config
        )
        # No XTRACT protocol is read: FSL tracts off, tractography on
        for tract in TRACTS:
            subject_config[DIL.DTI][tract] = "false"
        subject_config[DIL.DTI]["tractography"] = "true"
        for (category, key), value in subject.items():
            subject_config[category][key] = value

        input_state_list = SubjectInputStateList(str(dicom_dir), global_config)
        for data_input in input_state_list:
            (dicom_dir / str(data_input)).mkdir()
            input_state_list[data_input].loaded = data_input not in unloaded
            input_state_list[data_input].volumes = (
                1 if data_input.value.max_volumes == 1 else 40
            )
        workflow = MainWorkflow(
            name="gates",
            base_dir=str(subject_dir),
            global_config=global_config,
            subject_config=subject_config,
            dependency_manager=DependencyManager(),
            subject_input_state_list=input_state_list,
            test_run=True,
        )
        return workflow._get_all_nodes()

    return _build


def _bias_corrected_bet(nodes):
    return {
        node.fullname
        for node in nodes
        if type(node.interface).__name__ == "BET" and node.inputs.reduce_bias is True
    }


@pytest.mark.parametrize(
    "deskull_engine, expected",
    [
        (DeskullEngine.ANTSPYNET, False),
        (DeskullEngine.SYNTHSTRIP, False),
        (DeskullEngine.BET, True),
    ],
)
def test_bet_bias_correction(build, deskull_engine, expected):
    nodes = build(
        {"deskull_engine": deskull_engine.name},
        {
            (category, "bet_bias_correction"): "true"
            for category in (DIL.T13D, DIL.FLAIR3D, DIL.MDC)
        },
    )
    corrected = _bias_corrected_bet(nodes)
    if expected:
        # the reference T1, the FLAIR and the post-contrast T1 deskull nodes
        assert len(corrected) >= 3
    else:
        assert corrected == set()


@pytest.mark.parametrize("flair_loaded", [False, True])
def test_flat1(build, flair_loaded):
    nodes = build(
        {},
        {(DIL.T13D, "flat1"): "true"},
        unloaded=() if flair_loaded else (DIL.FLAIR3D,),
    )
    has_flat1 = any(node.fullname.startswith("FLAT1.") for node in nodes)
    assert has_flat1 is flair_loaded


@pytest.mark.parametrize(
    "tractography_engine, expected",
    [
        (TractographyEngine.DIPY_RECOBUNDLES, False),
        (TractographyEngine.FSL_XTRACT, True),
    ],
)
def test_old_eddy_correct(build, tractography_engine, expected):
    nodes = build(
        {"tractography_engine": tractography_engine.name},
        {(DIL.DTI, "old_eddy_correct"): "true"},
    )
    has_eddy_correct = any(
        type(node.interface).__name__ == "EddyCorrect" for node in nodes
    )
    assert has_eddy_correct is expected


@pytest.mark.parametrize(
    "tractography_engine, expected",
    [
        (TractographyEngine.FSL_XTRACT, False),
        (TractographyEngine.DIPY_RECOBUNDLES, True),
    ],
)
def test_cingulum(build, tractography_engine, expected):
    nodes = build(
        {"tractography_engine": tractography_engine.name},
        {(DIL.DTI, "cingulum"): "true"},
    )
    has_cingulum = any("cingulum" in node.fullname for node in nodes)
    assert has_cingulum is expected


@pytest.fixture
def fsl_only_tract(tmp_path, monkeypatch):
    """An FSL-only tract with an XTRACT protocol, whether or not FSL is
    installed: a disposable protocol folder replaces the XTRACT data."""
    tract = "atr"
    assert tract not in DIPY_TRACT_ATLAS
    if tract not in TRACTS:
        monkeypatch.setitem(
            TRACTS, tract, ["Anterior Thalamic Radiation", "false", DEFAULT_N_SAMPLES]
        )
    monkeypatch.setitem(WF_PREFERENCES[DIL.DTI], tract, tract_preference_entry(tract))
    xtract_dir = tmp_path / "xtract_data"
    for side in ("l", "r"):
        protocol_dir = xtract_dir / ("%s_%s" % (tract, side))
        protocol_dir.mkdir(parents=True)
        (protocol_dir / "seed.nii.gz").touch()
        (protocol_dir / "target.nii.gz").touch()
    monkeypatch.setattr(tractography_workflow, "XTRACT_DATA_DIR", str(xtract_dir))
    return tract


@pytest.mark.parametrize(
    "tractography_engine, expected",
    [
        (TractographyEngine.DIPY_RECOBUNDLES, False),
        (TractographyEngine.FSL_XTRACT, True),
    ],
)
def test_fsl_only_tract(build, fsl_only_tract, tractography_engine, expected):
    nodes = build(
        {"tractography_engine": tractography_engine.name},
        {(DIL.DTI, fsl_only_tract): "true"},
    )
    has_tract = any(
        node.fullname.startswith("tract_%s." % fsl_only_tract) for node in nodes
    )
    assert has_tract is expected
