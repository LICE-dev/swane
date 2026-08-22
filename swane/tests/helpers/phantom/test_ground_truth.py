"""The phantom ground truth must cache and reload identically to a rebuild.

Two layers, matching the two ways the ground truth is obtained:

* fast, no FreeSurfer -- ``compute_centres`` on a hand-built tiny tissue model,
  the JSON round-trip, and the load/fallback decision in ``GroundTruth.load``;
* heavy, needs ``fsaverage`` -- the cached sidecar built with the phantom must
  equal what ``GroundTruth.build`` recomputes from scratch, so switching the
  sweep from rebuild to load cannot change a single graded coordinate.
"""

import os

import numpy as np
import pytest

from swane.tests.helpers.phantom.ground_truth import (
    GROUND_TRUTH_FILENAME,
    build_centres,
    compute_centres,
    load_centres,
    save_ground_truth,
)
from swane.tests.helpers.phantom.tissue import TissueClass, TissueModel


def _has_fsaverage() -> bool:
    home = os.environ.get("FREESURFER_HOME")
    if not home:
        return False
    return os.path.isdir(os.path.join(home, "subjects", "fsaverage", "mri"))


def _synthetic_model() -> TissueModel:
    """A tiny hand-built tissue model, enough to exercise ``compute_centres``.

    A 10^3 grid with an affine that centres RAS x on zero, so the venous sinus
    voxels straddle both hemispheres and the L/R split has something to divide.
    """
    shape = (10, 10, 10)
    labels = np.full(shape, TissueClass.AIR, dtype=np.int16)
    labels[2:8, 2:8, 2:8] = TissueClass.WM  # brain bulk
    labels[4:6, 4:6, 4:6] = TissueClass.CORTICAL_GM
    # A slab of venous sinus spanning x, so both hemispheres are populated.
    labels[1:9, 5, 6] = TissueClass.VENOUS_SINUS

    precentral = np.zeros(shape, dtype=bool)
    precentral[4:6, 4:6, 7] = True
    cst = np.zeros(shape, dtype=bool)
    cst[5, 5, 2:8] = True

    # voxel -> RAS with the origin at the grid centre: x in [-5, 4].
    affine = np.array(
        [
            [1.0, 0.0, 0.0, -5.0],
            [0.0, 1.0, 0.0, -5.0],
            [0.0, 0.0, 1.0, -5.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    return TissueModel(
        labels=labels,
        affine=affine,
        zooms=(1.0, 1.0, 1.0),
        precentral=precentral,
        cst=cst,
    )


def test_compute_centres_returns_expected_features():
    centres = compute_centres(_synthetic_model())
    for key in ("brain", "precentral", "cst", "venous_sinus", "seeg"):
        assert key in centres, "missing centroid %r" % key
        assert np.asarray(centres[key]).shape == (3,)
    # The venous slab straddles x = 0, so both hemisphere centroids exist and
    # sit on the correct sides.
    assert centres["venous_sinus_L"][0] < 0
    assert centres["venous_sinus_R"][0] > 0


def test_save_load_round_trip_is_exact(tmp_path):
    centres = compute_centres(_synthetic_model())
    save_ground_truth(str(tmp_path), centres)
    assert (tmp_path / GROUND_TRUTH_FILENAME).is_file()

    reloaded = load_centres(str(tmp_path))
    assert reloaded is not None
    assert set(reloaded) == set(centres)
    for key in centres:
        assert np.allclose(reloaded[key], centres[key]), key


def test_load_centres_missing_returns_none(tmp_path):
    assert load_centres(str(tmp_path)) is None


def test_ground_truth_load_uses_cache_without_rebuilding(tmp_path, monkeypatch):
    """A present sidecar is used verbatim; the expensive rebuild never runs."""
    from swane.tests.prerelease import checks

    centres = compute_centres(_synthetic_model())
    save_ground_truth(str(tmp_path), centres)

    def _fail(*_args, **_kwargs):
        raise AssertionError("build_centres must not be called when a sidecar exists")

    monkeypatch.setattr(checks, "build_centres", _fail)
    truth = checks.GroundTruth.load(str(tmp_path))
    for key in centres:
        assert np.allclose(truth.centres[key], centres[key]), key


def test_ground_truth_load_falls_back_to_build_when_missing(tmp_path, monkeypatch):
    """No sidecar (an old cache) -> recompute from the tissue model."""
    from swane.tests.prerelease import checks

    sentinel = {"brain": np.array([1.0, 2.0, 3.0])}
    monkeypatch.setattr(checks, "build_centres", lambda *_a, **_k: sentinel)
    truth = checks.GroundTruth.load(str(tmp_path))
    assert truth.centres is sentinel


def test_ground_truth_load_none_dir_builds(monkeypatch):
    """The checks-only path passes no phantom root and must still build."""
    from swane.tests.prerelease import checks

    sentinel = {"brain": np.array([0.0, 0.0, 0.0])}
    monkeypatch.setattr(checks, "build_centres", lambda *_a, **_k: sentinel)
    assert checks.GroundTruth.load(None).centres is sentinel


@pytest.mark.heavy
@pytest.mark.skipif(
    not _has_fsaverage(),
    reason="needs $FREESURFER_HOME/subjects/fsaverage to build the phantom",
)
def test_cached_sidecar_matches_rebuild(tmp_path):
    """The whole point: load == rebuild, to the coordinate.

    Building the model once and caching its centroids must give exactly what
    recomputing the model would, or the sweep would grade against a subtly
    different reference after the load optimisation.
    """
    from swane.tests.prerelease.checks import GroundTruth

    centres = build_centres()
    save_ground_truth(str(tmp_path), centres)

    cached = GroundTruth.load(str(tmp_path)).centres
    rebuilt = GroundTruth.build().centres
    assert set(cached) == set(rebuilt)
    for key in rebuilt:
        assert np.allclose(cached[key], rebuilt[key], atol=1e-6), key
