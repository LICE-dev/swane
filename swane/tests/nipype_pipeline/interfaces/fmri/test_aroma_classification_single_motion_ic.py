"""Regression test: ICA-AROMA classification with exactly one motion IC.

ica_aroma_py 0.1.3 returned a scalar instead of a list from
``AromaClassification`` when a single component was classified as motion,
which Nipype rejected with a ``TraitError`` on the ``motion_ics`` output.
"""

import numpy as np
import pytest
from ica_aroma_py.services.ICA_AROMA_nodes import AromaClassification


def _run_classification(tmp_path, monkeypatch, csf_fract):
    monkeypatch.chdir(tmp_path)
    n = len(csf_fract)
    node = AromaClassification()
    node.inputs.max_rp_corr = np.zeros(n)
    node.inputs.edge_fract = np.zeros(n)
    node.inputs.HFC = np.zeros(n)
    node.inputs.csf_fract = np.array(csf_fract, dtype=float)
    return node.run().outputs


def test_exactly_one_motion_ic_gives_a_list(tmp_path, monkeypatch):
    outputs = _run_classification(tmp_path, monkeypatch, [0.0, 0.5, 0.0, 0.0])
    assert outputs.motion_ics == [2]
    assert (tmp_path / "classified_motion_ICs.txt").read_text() == "2"


@pytest.mark.parametrize(
    "csf_fract, expected",
    [([0.0, 0.0, 0.0], []), ([0.5, 0.0, 0.5], [1, 3])],
)
def test_zero_or_several_motion_ics_give_a_list(
    tmp_path, monkeypatch, csf_fract, expected
):
    outputs = _run_classification(tmp_path, monkeypatch, csf_fract)
    assert outputs.motion_ics == expected
