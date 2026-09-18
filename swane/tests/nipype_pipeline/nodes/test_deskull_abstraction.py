import pytest

from swane.config.config_enums import DeskullEngine, DeskullModality, SegmentationEngine
from swane.nipype_pipeline.nodes.utils import (
    get_deskull_node,
    resolve_deskull_engine,
    resolve_segmentation_engine,
)
from swane.nipype_pipeline.nodes.AntsPyNetBrainExtraction import (
    AntsPyNetBrainExtraction,
)
from swane.nipype_pipeline.nodes.SynthStrip import SynthStrip
from nipype.interfaces.fsl import BET


class _Cfg(dict):
    def getenum_safe(self, key):
        return self[key]


def test_resolve_prefers_configured_engine():
    cfg = _Cfg(deskull_engine=DeskullEngine.BET)
    assert resolve_deskull_engine(cfg) == DeskullEngine.BET


def test_resolve_folds_synthstrip_when_excluded():
    cfg = _Cfg(deskull_engine=DeskullEngine.SYNTHSTRIP)
    assert (
        resolve_deskull_engine(cfg, allow_synthstrip=False) == DeskullEngine.ANTSPYNET
    )
    # honoured when allowed
    assert (
        resolve_deskull_engine(cfg, allow_synthstrip=True) == DeskullEngine.SYNTHSTRIP
    )


def test_resolve_leaves_antspynet_and_bet_under_exclusion():
    for eng in (DeskullEngine.ANTSPYNET, DeskullEngine.BET):
        cfg = _Cfg(deskull_engine=eng)
        assert resolve_deskull_engine(cfg, allow_synthstrip=False) == eng


def test_get_deskull_node_dispatches_by_engine():
    a = get_deskull_node(
        name="x",
        deskull_engine=DeskullEngine.ANTSPYNET,
        deskull_modality=DeskullModality.T1,
        mask=True,
    )
    assert isinstance(a.interface, AntsPyNetBrainExtraction)
    assert a.name == "x_antspynet"
    assert a.inputs.modality == "t1"

    s = get_deskull_node(name="x", deskull_engine=DeskullEngine.SYNTHSTRIP, mask=True)
    assert isinstance(s.interface, SynthStrip)
    assert s.name == "x_synthstrip"

    b = get_deskull_node(
        name="x", deskull_engine=DeskullEngine.BET, bet_thr=0.3, mask=True
    )
    assert isinstance(b.interface, BET)
    assert b.name == "x_bet"


def test_get_deskull_node_forwards_antspynet_threshold():
    n = get_deskull_node(
        name="x",
        deskull_engine=DeskullEngine.ANTSPYNET,
        deskull_modality=DeskullModality.T1,
        mask=True,
        antspynet_thr=0.6,
    )
    assert n.inputs.threshold == 0.6


def test_get_deskull_node_antspynet_threshold_defaults_unset():
    n = get_deskull_node(
        name="x",
        deskull_engine=DeskullEngine.ANTSPYNET,
        deskull_modality=DeskullModality.T1,
        mask=True,
    )
    # left unset -> node uses its own 0.5 default
    from nipype.interfaces.base import isdefined

    assert not isdefined(n.inputs.threshold) or n.inputs.threshold == 0.5


class _FakeSection:
    def __init__(self, value):
        self._value = value

    def getenum_safe(self, key):
        assert key == "segmentation_engine"
        return self._value


def test_resolve_segmentation_engine_passthrough_ants():
    cfg = _FakeSection(SegmentationEngine.ANTS)
    assert resolve_segmentation_engine(cfg) is SegmentationEngine.ANTS


def test_resolve_segmentation_engine_passthrough_fsl():
    cfg = _FakeSection(SegmentationEngine.FSL)
    assert resolve_segmentation_engine(cfg) is SegmentationEngine.FSL
