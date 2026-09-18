"""Phantom tests for the per-bundle recovery metric and gate logic.

Pure-function level: synthetic straight-line streamlines, no real subject data.
"""

import numpy as np
import pytest
from nipype.interfaces.base import isdefined

from swane.nipype_pipeline.interfaces.dipy.DipyBundleRecovery import (
    precision_recall_f5,
    recovery_arm,
    adjusted_params,
    is_low_confidence,
    PR_THR_MM,
    PREC_CONTAMINATED,
    REC_PRESENT,
    TIGHTEN_R_PRUNING_THR,
    WIDEN_REDUCTION_THR,
    MIN_COUNT,
)


def _lines(xs, z0=0.0, z1=50.0, n=20, shift=(0.0, 0.0, 0.0)):
    """A bundle of straight streamlines parallel to z, one per x in ``xs``."""
    z = np.linspace(z0, z1, n)
    out = []
    for x in xs:
        line = np.stack([np.full(n, x), np.zeros(n), z], axis=1).astype(float)
        out.append(line + np.asarray(shift, float))
    return out


class TestPrecisionRecallF5:
    def test_identical_bundles_score_one(self):
        model = _lines([0, 5, 10, 15])
        prec, rec, f5 = precision_recall_f5(model, model)
        assert (prec, rec, f5) == (1.0, 1.0, 1.0)

    def test_far_apart_bundles_score_zero(self):
        model = _lines([0, 5, 10])
        far = _lines([0, 5, 10], shift=(100.0, 0.0, 0.0))  # 100 mm away
        assert precision_recall_f5(far, model) == (0.0, 0.0, 0.0)

    def test_extra_far_streamlines_drop_precision_not_recall(self):
        model = _lines([0, 5, 10, 15])
        # the model lines plus four far ones: recall stays 1, precision ~ 1/2
        recognized = model + _lines([0, 5, 10, 15], shift=(100.0, 0.0, 0.0))
        prec, rec, f5 = precision_recall_f5(recognized, model)
        assert rec == 1.0
        assert prec == pytest.approx(0.5, abs=1e-6)
        assert 0.0 < f5 < 1.0

    def test_subset_covers_less_of_the_model_recall_below_one(self):
        model = _lines([0, 5, 10, 15])
        recognized = _lines([0, 5])  # only half the model's lines are near one
        prec, rec, _ = precision_recall_f5(recognized, model)
        assert prec == 1.0
        assert rec == pytest.approx(0.5, abs=1e-6)

    def test_empty_recognized_scores_zero(self):
        assert precision_recall_f5([], _lines([0])) == (0.0, 0.0, 0.0)

    def test_matching_uses_the_5mm_threshold(self):
        model = _lines([0.0])
        near = _lines([PR_THR_MM - 1.0])  # 4 mm away -> matches
        far = _lines([PR_THR_MM + 1.0])  # 6 mm away -> does not
        assert precision_recall_f5(near, model)[0] == 1.0
        assert precision_recall_f5(far, model)[0] == 0.0


class TestRecoveryArm:
    def test_scarce_bundle_is_widened(self):
        # recall below REC_PRESENT -> widen, regardless of precision
        assert recovery_arm(1.0, REC_PRESENT - 0.01) == "widen"
        assert recovery_arm(0.0, 0.0) == "widen"

    def test_contaminated_bundle_is_tightened(self):
        # low precision but recall present -> tighten
        assert recovery_arm(PREC_CONTAMINATED - 0.01, REC_PRESENT + 0.1) == "tighten"

    def test_good_bundle_is_left_alone(self):
        assert recovery_arm(PREC_CONTAMINATED + 0.1, REC_PRESENT + 0.1) is None

    def test_arms_are_exclusive(self):
        for prec in (0.0, 0.1, 0.3, 0.9):
            for rec in (0.0, 0.2, 0.5, 1.0):
                arm = recovery_arm(prec, rec)
                assert arm in (None, "tighten", "widen")


class TestAdjustedParams:
    def _base(self):
        return {
            "model_clust_thr": 2.5,
            "reduction_thr": 15.0,
            "pruning_thr": 8.0,
            "refine": True,
            "r_reduction_thr": 12.0,
            "r_pruning_thr": 6.0,
        }

    def test_tighten_lowers_only_refine_pruning(self):
        base = self._base()
        out = adjusted_params(base, "tighten")
        assert out["r_pruning_thr"] == TIGHTEN_R_PRUNING_THR
        assert out["reduction_thr"] == base["reduction_thr"]

    def test_widen_raises_only_first_pass_reduction(self):
        base = self._base()
        out = adjusted_params(base, "widen")
        assert out["reduction_thr"] == WIDEN_REDUCTION_THR
        assert out["r_pruning_thr"] == base["r_pruning_thr"]

    def test_none_arm_is_an_unchanged_copy(self):
        base = self._base()
        out = adjusted_params(base, None)
        assert out == base

    def test_does_not_mutate_the_input(self):
        base = self._base()
        adjusted_params(base, "tighten")
        adjusted_params(base, "widen")
        assert base["r_pruning_thr"] == 6.0
        assert base["reduction_thr"] == 15.0


class TestLowConfidenceFlag:
    def test_too_few_streamlines_is_flagged(self):
        assert is_low_confidence(1.0, 1.0, MIN_COUNT - 1) is True

    def test_displaced_bundle_both_axes_low_is_flagged(self):
        assert (
            is_low_confidence(PREC_CONTAMINATED - 0.05, REC_PRESENT - 0.05, 500) is True
        )

    def test_covered_bundle_is_not_flagged(self):
        assert is_low_confidence(0.5, 0.6, 500) is False

    def test_precise_but_scarce_is_not_flagged_when_present(self):
        # recall at/above the gate with enough streamlines -> not flagged
        assert is_low_confidence(0.5, REC_PRESENT + 0.01, 500) is False


# --------------------------------------------------------------------------- #
# Node integration: the recovery node with a real recognition retry.
# --------------------------------------------------------------------------- #
import os

from swane.nipype_pipeline.interfaces.dipy.DipyRecoBundles import (
    DipyRecoBundlesBuild,
    bundle_path,
)
from swane.nipype_pipeline.interfaces.dipy.DipyBundleRecovery import DipyBundleRecovery

_MODEL_SHAPE = ([-20, 0, 0], [0, 0, 1])  # the atlas model's shape
_FAR_SHAPE = ([80, 80, 0], [0, 1, 0])  # far from the model -> metric ~0
_NOISE_A = ([60, -40, 10], [1, 1, 0])
_NOISE_B = ([10, 50, -20], [0, 1, 1])


def _bundle(rng, n, base, direction, jitter=3, length=80, npts=40):
    base = np.asarray(base, float)
    direction = np.asarray(direction, float)
    direction /= np.linalg.norm(direction)
    t = np.linspace(0, length, npts)[:, None]
    out = []
    for _ in range(n):
        off = base + rng.normal(0, jitter, 3)
        out.append(
            (off + t * direction + rng.normal(0, 0.5, (npts, 3))).astype(np.float32)
        )
    return out


def _make_streamlines(*groups):
    from dipy.tracking.streamline import Streamlines

    lines = []
    for g in groups:
        lines.extend(g)
    return Streamlines(lines)


def _save(streamlines, path):
    import nibabel as nib
    from dipy.io.stateful_tractogram import StatefulTractogram, Space
    from dipy.io.streamline import save_tractogram

    ref = nib.Nifti1Image(np.zeros((200, 200, 200), dtype=np.float32), np.eye(4))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_tractogram(
        StatefulTractogram(streamlines, ref, Space.RASMM), path, bbox_valid_check=False
    )


def _n(trx_path):
    from dipy.io.streamline import load_tractogram

    return len(load_tractogram(trx_path, "same", bbox_valid_check=False).streamlines)


@pytest.fixture
def atlas_dir(tmp_path):
    base = tmp_path / "atlas"
    rng = np.random.default_rng(7)
    _save(
        _make_streamlines(_bundle(rng, 120, *_MODEL_SHAPE)),
        bundle_path(str(base), "IFOF_R"),
    )
    return str(base)


def _build_chunk(streamlines, tmp_path, name):
    chunk = str(tmp_path / ("%s.trx" % name))
    _save(streamlines, chunk)
    node = DipyRecoBundlesBuild()
    node.inputs.tractogram_chunk = chunk
    node.inputs.num_threads = 1
    node.inputs.out_pickle = str(tmp_path / ("%s.pkl" % name))
    node.run()
    return chunk, node._list_outputs()["recobundles_pickle"]


def _run_recovery(default_bundle, chunk, pkl, atlas_dir, tmp_path):
    node = DipyBundleRecovery()
    node.inputs.default_bundle = default_bundle
    node.inputs.recobundles_pickles = [pkl]
    node.inputs.tractogram_chunks = [chunk]
    node.inputs.atlas_dir = atlas_dir
    node.inputs.model_bundle_name = "IFOF_R"
    node.inputs.num_threads = 1
    node.inputs.out_bundle = str(tmp_path / "recovered.trx")
    node.run()
    return node


class TestRecoveryNode:
    def test_good_default_is_kept_unchanged_and_not_flagged(self, atlas_dir, tmp_path):
        rng = np.random.default_rng(1)
        model_like = _make_streamlines(_bundle(rng, 120, *_MODEL_SHAPE))
        default = str(tmp_path / "default.trx")
        _save(model_like, default)
        # arm is None here, so these are never read -- but must exist.
        chunk, pkl = _build_chunk(
            _make_streamlines(_bundle(rng, 60, *_MODEL_SHAPE)), tmp_path, "dummy"
        )
        node = _run_recovery(default, chunk, pkl, atlas_dir, tmp_path)
        outs = node._list_outputs()
        assert os.path.exists(outs["bundle"])
        assert _n(outs["bundle"]) == len(model_like)  # default kept as-is
        assert not isdefined(outs["confidence_flag"])
        assert not os.path.exists(node._gen_flagname())

    def test_displaced_default_is_recovered_by_the_retry(self, atlas_dir, tmp_path):
        rng = np.random.default_rng(2)
        far = _make_streamlines(_bundle(rng, 20, *_FAR_SHAPE))  # metric ~0 -> widen
        default = str(tmp_path / "default.trx")
        _save(far, default)
        subject = _make_streamlines(
            _bundle(rng, 250, *_MODEL_SHAPE),  # the real bundle is in the subject
            _bundle(rng, 300, *_NOISE_A, jitter=5),
        )
        chunk, pkl = _build_chunk(subject, tmp_path, "subject")
        node = _run_recovery(default, chunk, pkl, atlas_dir, tmp_path)
        outs = node._list_outputs()
        # the retry found the real bundle: far more streamlines than the default,
        # and good enough coverage that it is not flagged.
        assert _n(outs["bundle"]) > len(far)
        assert not isdefined(outs["confidence_flag"])

    def test_unrecoverable_default_is_flagged(self, atlas_dir, tmp_path):
        rng = np.random.default_rng(3)
        far = _make_streamlines(_bundle(rng, 20, *_FAR_SHAPE))
        default = str(tmp_path / "default.trx")
        _save(far, default)
        noise = _make_streamlines(
            _bundle(rng, 400, *_NOISE_A, jitter=5),
            _bundle(rng, 400, *_NOISE_B, jitter=5),
        )
        chunk, pkl = _build_chunk(noise, tmp_path, "noise_only")
        node = _run_recovery(default, chunk, pkl, atlas_dir, tmp_path)
        outs = node._list_outputs()
        assert isdefined(outs["confidence_flag"])
        assert os.path.exists(outs["confidence_flag"])
        import json

        data = json.load(open(outs["confidence_flag"]))
        assert data["low_confidence"] is True
        assert data["model_bundle"] == "IFOF_R"
