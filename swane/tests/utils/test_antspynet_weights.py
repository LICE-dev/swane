import os
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


def _capture_child_env(monkeypatch):
    calls = []
    monkeypatch.setattr(
        antspynet_weights.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(kwargs["env"]),
    )
    monkeypatch.setattr(antspynet_weights, "weights_are_fetched", lambda x: False)
    antspynet_weights.preload_weights(["brainExtractionRobustT1"])
    return calls[0]


def test_preload_points_the_child_at_certifi_bundle(monkeypatch):
    # python.org macOS Pythons have no CA store: the child needs certifi's.
    import certifi

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    assert _capture_child_env(monkeypatch)["SSL_CERT_FILE"] == certifi.where()


def test_preload_keeps_a_user_configured_ca_bundle(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
    assert _capture_child_env(monkeypatch)["SSL_CERT_FILE"] == "/custom/ca.pem"


def _populate_cache(directory, names=("brainExtractionRobustT1",)):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / (name + ".h5")).touch()
    (directory / (antspynet_weights.TEMPLATE_NAME + ".nii.gz")).touch()


def test_cache_dir_matches_the_antspynet_default():
    # antspynet 0.3.2 default; the heavy test below guards against upstream drift.
    assert antspynet_weights.ANTSXNET_CACHE_DIR == os.path.join(
        os.path.expanduser("~"), ".keras", "ANTsXNet"
    )


def test_weights_are_fetched_checks_only_the_swane_cache_dir(tmp_path, monkeypatch):
    ours = tmp_path / "ours"
    monkeypatch.setattr(antspynet_weights, "ANTSXNET_CACHE_DIR", str(ours))
    names = ["brainExtractionRobustT1"]

    assert not antspynet_weights.weights_are_fetched(names)
    _populate_cache(ours)
    assert antspynet_weights.weights_are_fetched(names)
    assert not antspynet_weights.weights_are_fetched(names + ["brainExtractionFLAIR"])


def test_weights_are_fetched_ignores_keras_home(tmp_path, monkeypatch):
    # antspynet never reads KERAS_HOME: weights there are invisible to the nodes.
    ours = tmp_path / "ours"
    elsewhere = tmp_path / "keras_home"
    _populate_cache(elsewhere / "ANTsXNet")
    monkeypatch.setattr(antspynet_weights, "ANTSXNET_CACHE_DIR", str(ours))
    monkeypatch.setenv("KERAS_HOME", str(elsewhere))

    assert not antspynet_weights.weights_are_fetched(["brainExtractionRobustT1"])

    # And a populated SWANe cache is enough whatever KERAS_HOME says.
    _populate_cache(ours)
    assert antspynet_weights.weights_are_fetched(["brainExtractionRobustT1"])


def test_weights_are_fetched_ignores_tmp_keras(tmp_path, monkeypatch):
    # Stale /tmp/.keras weights used to make the pre-fetch skip.
    monkeypatch.setattr(antspynet_weights, "ANTSXNET_CACHE_DIR", str(tmp_path / "x"))
    real_isdir = os.path.isdir
    monkeypatch.setattr(
        os.path,
        "isdir",
        lambda p: True if str(p).startswith("/tmp/.keras") else real_isdir(p),
    )
    monkeypatch.setattr(
        os.path,
        "exists",
        lambda p: True if str(p).startswith("/tmp/.keras") else os.path.lexists(p),
    )
    assert not antspynet_weights.weights_are_fetched(["brainExtractionRobustT1"])


@pytest.fixture
def fake_antspynet_utilities(monkeypatch):
    """Fake ``antspynet.utilities`` recording every call, in order."""
    import types

    calls = []
    utilities = types.ModuleType("antspynet.utilities")
    utilities.set_antsxnet_cache_directory = lambda d: calls.append(("set", d))
    utilities.get_pretrained_network = lambda n: calls.append(("network", n))
    utilities.get_antsxnet_data = lambda n: calls.append(("data", n))
    package = types.ModuleType("antspynet")
    package.utilities = utilities
    monkeypatch.setitem(sys.modules, "antspynet", package)
    monkeypatch.setitem(sys.modules, "antspynet.utilities", utilities)
    return calls


def test_pin_sets_the_swane_cache_dir_in_antspynet(fake_antspynet_utilities):
    antspynet_weights.pin_antsxnet_cache_dir()
    assert fake_antspynet_utilities == [("set", antspynet_weights.ANTSXNET_CACHE_DIR)]


def test_fetch_pins_the_cache_dir_before_downloading(fake_antspynet_utilities):
    antspynet_weights.fetch_weights(["brainExtractionRobustT1"])
    assert fake_antspynet_utilities == [
        ("set", antspynet_weights.ANTSXNET_CACHE_DIR),
        ("network", "brainExtractionRobustT1"),
        ("data", antspynet_weights.TEMPLATE_NAME),
    ]


@pytest.mark.heavy
def test_swane_cache_dir_matches_the_installed_antspynet_default():
    """If this fails after an antspynet upgrade, its default moved: SWANe's
    constant is still what both the pre-fetch and the nodes use (they pin it),
    but the previous cache would be left behind -- decide whether to migrate."""
    import importlib.util

    # Not importorskip: importing antspynet loads TensorFlow, which must stay
    # out of the long-lived pytest process (and can hang there on macOS).
    if importlib.util.find_spec("antspynet") is None:
        pytest.skip("antspynet is not installed")
    # Read in a fresh child: another test may already have pinned this process.
    # The child dumps its stack and exits before the timeout, so a hang in the
    # TensorFlow import is reported instead of eating the whole CI budget.
    child = (
        "import faulthandler;"
        "faulthandler.dump_traceback_later(240, exit=True);"
        "from antspynet.utilities import get_antsxnet_cache_directory;"
        "print(get_antsxnet_cache_directory())"
    )
    result = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.strip().splitlines()[-1] == (
        antspynet_weights.ANTSXNET_CACHE_DIR
    )
