import subprocess
import sys

import pytest
from nipype import Node, Workflow
from nipype.interfaces.utility import IdentityInterface

from swane.config.config_enums import DeskullModality
from swane.nipype_pipeline.interfaces.ants.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
from swane.utils import antspynet_weights


def _deskull_node(name, modality=None):
    node = Node(AntsPyNetBrainExtraction(), name=name)
    if modality is not None:
        node.inputs.modality = modality
    return node


def test_every_deskull_modality_has_a_known_network():
    # A DeskullModality missing here would silently skip its pre-fetch and let
    # the node download inside a worker again.
    for modality in DeskullModality:
        assert modality.value in antspynet_weights.WEIGHTS_BY_MODALITY


def test_weight_names_dedupes_and_ignores_unknown_keys():
    names = antspynet_weights.weight_names(["bold", "t1", "bold", "not-a-modality"])
    assert names == ["brainExtractionRobustBOLD", "brainExtractionRobustT1"]


def test_workflow_modalities_walks_nested_workflows(tmp_path):
    inner = Workflow(name="inner")
    inner.add_nodes(
        [
            _deskull_node("flair_deskull", DeskullModality.FLAIR.value),
            _deskull_node("t1_deskull_again", DeskullModality.T1.value),
        ]
    )
    outer = Workflow(name="outer", base_dir=str(tmp_path))
    outer.add_nodes(
        [
            _deskull_node("t1_deskull", DeskullModality.T1.value),
            # Not wired to a modality: nothing to pre-fetch for it.
            _deskull_node("undefined_modality"),
            Node(IdentityInterface(fields=["x"]), name="other"),
            inner,
        ]
    )

    assert antspynet_weights.workflow_modalities(outer) == ["flair", "t1"]


def test_workflow_without_antspynet_nodes_needs_nothing(tmp_path):
    workflow = Workflow(name="plain", base_dir=str(tmp_path))
    workflow.add_nodes([Node(IdentityInterface(fields=["x"]), name="other")])
    assert antspynet_weights.workflow_modalities(workflow) == []


def test_preload_runs_in_an_exec_child_and_raises_on_failure(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        raise subprocess.CalledProcessError(1, cmd, stderr="offline")

    monkeypatch.setattr(antspynet_weights.subprocess, "run", fake_run)
    monkeypatch.setattr(antspynet_weights, "weights_are_fetched", lambda x: False)
    with pytest.raises(subprocess.CalledProcessError):
        antspynet_weights.preload_weights(["brainExtractionRobustT1"])

    cmd, kwargs = calls[0]
    assert cmd[0] == sys.executable
    assert cmd[-1] == "brainExtractionRobustT1"
    assert kwargs["check"] is True
