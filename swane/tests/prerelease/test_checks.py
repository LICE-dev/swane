"""Unit coverage for the pure-logic parts of :mod:`swane.tests.prerelease.checks`.

These run without the phantom or the pipeline: they build a subject directory
by hand and feed a synthetic :class:`PassResult` to a single check, asserting
it reads the *real* on-disk layout the workflow produces. The dipy bundle check
is here specifically because it once looked in the wrong directory for the wrong
filenames and so silently emitted no checks -- a green pass that validated
nothing. A directory-shape regression must fail loudly instead of vanishing.
"""

import json
import os

import nibabel as nib
import numpy as np

from swane.tests.prerelease.checks import (
    _check_dipy_bundle_recovery,
    _check_fmri_resting_networks,
    _check_fmri_task_location,
    _check_no_mapnode_subfolder,
    GroundTruth,
    RESULTS_DIR,
    WARNING,
)
from swane.tests.prerelease.runner import PassResult
from swane.tests.prerelease.subject import SWEEP_TRACT


def _dipy_result(subject_dir: str) -> PassResult:
    return PassResult(name="dti_tractography_dipy", subject_dir=subject_dir)


def _dti_results_dir(subject_dir: str) -> str:
    # Where MainWorkflow.launch_dipy_dti_analysis sinks the bundles.
    path = os.path.join(subject_dir, RESULTS_DIR, "dti")
    os.makedirs(path, exist_ok=True)
    return path


def _by_name(checks) -> dict:
    return {c.name: c for c in checks}


def test_dipy_bundle_recovery_skips_other_passes(tmp_path):
    # The check is dipy-specific; an FSL/xtract pass must not produce any of its
    # results, whatever is on disk.
    result = PassResult(name="dti_tractography", subject_dir=str(tmp_path))
    assert _check_dipy_bundle_recovery(result, []) == []


def test_dipy_bundle_recovery_emits_nothing_without_the_dti_dir(tmp_path):
    # No results/dti at all: the check has nothing to look at and returns [].
    result = _dipy_result(str(tmp_path))
    assert _check_dipy_bundle_recovery(result, []) == []


def test_dipy_bundle_recovery_passes_when_both_bundles_present(tmp_path):
    dti = _dti_results_dir(str(tmp_path))
    for side in ("lh", "rh"):
        open(os.path.join(dti, "r-%s_%s.vtp" % (SWEEP_TRACT, side)), "w").close()

    checks = _by_name(_check_dipy_bundle_recovery(_dipy_result(str(tmp_path)), []))

    # Two sides -> recovery + confidence for each. Nothing is missing, no sidecar
    # was written, so every check passes.
    assert len(checks) == 4
    for side in ("lh", "rh"):
        assert checks["dipy.recovery.%s_%s" % (SWEEP_TRACT, side)].passed
        assert checks["dipy.confidence.%s_%s" % (SWEEP_TRACT, side)].passed


def test_dipy_bundle_recovery_fails_when_a_bundle_is_missing(tmp_path):
    dti = _dti_results_dir(str(tmp_path))
    # Only the left bundle was produced.
    open(os.path.join(dti, "r-%s_lh.vtp" % SWEEP_TRACT), "w").close()

    checks = _by_name(_check_dipy_bundle_recovery(_dipy_result(str(tmp_path)), []))

    assert checks["dipy.recovery.%s_lh" % SWEEP_TRACT].passed
    assert not checks["dipy.recovery.%s_rh" % SWEEP_TRACT].passed


def test_dipy_bundle_recovery_flags_a_low_confidence_bundle(tmp_path):
    dti = _dti_results_dir(str(tmp_path))
    for side in ("lh", "rh"):
        open(os.path.join(dti, "r-%s_%s.vtp" % (SWEEP_TRACT, side)), "w").close()
    # DipyBundleRecovery always writes this sidecar; only rh is low-confidence.
    for side, low in (("lh", False), ("rh", True)):
        with open(
            os.path.join(dti, "r-%s_%s.conf.json" % (SWEEP_TRACT, side)), "w"
        ) as f:
            json.dump(
                {
                    "precision": 0.0,
                    "recall": 0.125,
                    "count": 13,
                    "retry_arm": "widen",
                    "low_confidence": low,
                },
                f,
            )

    checks = _by_name(_check_dipy_bundle_recovery(_dipy_result(str(tmp_path)), []))

    # The bundle still exists (recovery passes) but is flagged (confidence fails).
    assert checks["dipy.recovery.%s_rh" % SWEEP_TRACT].passed
    assert checks["dipy.confidence.%s_lh" % SWEEP_TRACT].passed
    assert not checks["dipy.confidence.%s_rh" % SWEEP_TRACT].passed
    # A flagged bundle is a warning, not a broken pass: the recovery mechanism
    # is doing its job (see _check_dipy_bundle_recovery's docstring).
    assert checks["dipy.confidence.%s_rh" % SWEEP_TRACT].severity == WARNING
    # The warning says what was measured, not the expected outcome.
    assert checks["dipy.confidence.%s_rh" % SWEEP_TRACT].detail == (
        "%s_rh flagged as low confidence: precision 0.00, recall 0.12, "
        "13 streamlines (retry: widen)" % SWEEP_TRACT
    )
    assert checks["dipy.confidence.%s_lh" % SWEEP_TRACT].detail == (
        "%s_lh is not flagged as low confidence" % SWEEP_TRACT
    )


def _rs_result(subject_dir, engine="FSL", **values):
    return PassResult(
        name="fmri_task_and_rest",
        subject_dir=subject_dir,
        inputs=["t13d", "fmri_resting_state"],
        values={"fmri_engine": engine, **values},
    )


def _task_result(subject_dir):
    return PassResult(
        name="fmri_task_and_rest",
        subject_dir=subject_dir,
        inputs=["t13d", "fmri_1"],
        values={"fmri_engine": "NILEARN"},
    )


#: Synthetic motor cortex centres on a grid whose world x = voxel i - 32
#: (affine below): left at x = -20, right at x = +20.
_TRUTH = GroundTruth(
    centres={
        "brain": np.zeros(3),
        "precentral_L": np.array([-20.0, 0.0, 0.0]),
        "precentral_R": np.array([20.0, 0.0, 0.0]),
    }
)
_AFFINE = np.array(
    [[1, 0, 0, -32], [0, 1, 0, -32], [0, 0, 1, -8], [0, 0, 0, 1]], dtype=float
)


def _blob(x_world):
    """A 5x5x5 suprathreshold cube centred at world (x_world, 0, 0)."""
    data = np.zeros((64, 64, 16), dtype=np.float32)
    i, j, k = int(x_world + 32), 32, 8
    data[i - 2 : i + 3, j - 2 : j + 3, k - 2 : k + 3] = 4.0
    return data


def _cluster_map(root, contrast, threshold, data):
    path = os.path.join(
        root,
        RESULTS_DIR,
        "fMRI_1",
        "r-fmri_1_cluster_%s_threshold%.1f.nii.gz" % (contrast, threshold),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nib.save(nib.Nifti1Image(data, _AFFINE), path)
    return path


def _location(checks):
    return {
        n: c
        for n, c in _by_name(checks).items()
        if n.startswith(("fmri.location", "fmri.lateralization"))
    }


def test_task_activation_on_the_contralateral_motor_cortex_passes(tmp_path):
    root = str(tmp_path)
    files = [
        _cluster_map(root, "Task_A_versus_Task_B", 3.1, _blob(-20)),
        _cluster_map(root, "Task_B_versus_Task_A", 3.1, _blob(20)),
    ]
    checks = _location(_check_fmri_task_location(_task_result(root), files, _TRUTH))
    assert set(checks) == {
        "fmri.lateralization.fmri_1_Task_A_versus_Task_B",
        "fmri.location.fmri_1_Task_A_versus_Task_B",
        "fmri.lateralization.fmri_1_Task_B_versus_Task_A",
        "fmri.location.fmri_1_Task_B_versus_Task_A",
    }
    assert all(c.passed for c in checks.values()), checks


def test_task_activation_on_the_wrong_side_fails(tmp_path):
    root = str(tmp_path)
    files = [_cluster_map(root, "Task_A_versus_Task_B", 3.1, _blob(20))]
    checks = _location(_check_fmri_task_location(_task_result(root), files, _TRUTH))
    assert not checks["fmri.lateralization.fmri_1_Task_A_versus_Task_B"].passed
    assert not checks["fmri.location.fmri_1_Task_A_versus_Task_B"].passed


def test_task_activation_far_from_the_motor_cortex_fails(tmp_path):
    # Right hemisphere for B, but far from the precentral centre.
    root = str(tmp_path)
    data = _blob(28)
    data = np.roll(data, 20, axis=1)  # 20 mm anterior
    files = [_cluster_map(root, "Task_B_versus_Task_A", 3.1, data)]
    checks = _location(_check_fmri_task_location(_task_result(root), files, _TRUTH))
    assert checks["fmri.lateralization.fmri_1_Task_B_versus_Task_A"].passed
    assert not checks["fmri.location.fmri_1_Task_B_versus_Task_A"].passed


def test_task_location_uses_the_lowest_nonempty_threshold(tmp_path):
    # The lowest threshold is empty and the next one is on the right side: the
    # check grades the first non-empty map, not the empty one.
    root = str(tmp_path)
    empty = np.zeros((64, 64, 16), dtype=np.float32)
    files = [
        _cluster_map(root, "Task_A_versus_Task_B", 3.1, empty),
        _cluster_map(root, "Task_A_versus_Task_B", 5.0, _blob(-20)),
        _cluster_map(root, "Task_A_versus_Task_B", 7.0, _blob(20)),
    ]
    checks = _location(_check_fmri_task_location(_task_result(root), files, _TRUTH))
    assert all(c.passed for c in checks.values()), checks


def test_task_contrast_empty_at_every_threshold_fails(tmp_path):
    root = str(tmp_path)
    empty = np.zeros((64, 64, 16), dtype=np.float32)
    files = [_cluster_map(root, "Task_A_versus_Task_B", 3.1, empty)]
    checks = _location(_check_fmri_task_location(_task_result(root), files, _TRUTH))
    assert not checks["fmri.location.fmri_1_Task_A_versus_Task_B"].passed


def test_old_ground_truth_sidecar_is_recomputed(tmp_path, monkeypatch):
    # A sidecar cached before the per-side motor cortex existed lacks it: the
    # loader must rebuild instead of silently skipping the location check.
    from swane.tests.helpers.phantom.ground_truth import save_ground_truth
    from swane.tests.prerelease import checks as checks_mod

    save_ground_truth(str(tmp_path), {"brain": np.zeros(3)})
    monkeypatch.setattr(
        checks_mod, "build_centres", lambda _fs=None: dict(_TRUTH.centres)
    )
    truth = GroundTruth.load(str(tmp_path))
    assert "precentral_L" in truth.centres


# --------------------------------------------------------------------------- #
# Resting-state network location (every engine)
# --------------------------------------------------------------------------- #
#: Motor and posterior network centres 40 mm apart on the _AFFINE grid: a
#: component fusing both lands 20 mm from each, beyond FEATURE_TOLERANCE_MM.
_RS_TRUTH = GroundTruth(
    centres={
        "brain": np.zeros(3),
        "precentral": np.array([0.0, 20.0, 0.0]),
        "rs_posterior": np.array([0.0, -20.0, 0.0]),
    }
)


def _rs_blob(*y_worlds, value=4.0):
    """5x5x5 suprathreshold cubes centred at world (0, y, 0) for each y."""
    data = np.zeros((64, 64, 16), dtype=np.float32)
    for y in y_worlds:
        i, j, k = 32, int(y + 32), 8
        data[i - 2 : i + 3, j - 2 : j + 3, k - 2 : k + 3] = value
    return data


def _rs_maps(root, *maps):
    files = []
    for idx, data in enumerate(maps, start=1):
        path = os.path.join(
            root, RESULTS_DIR, "fMRI_resting_state", "r-thresh_zstat%02d.nii.gz" % idx
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        nib.save(nib.Nifti1Image(data, _AFFINE), path)
        files.append(path)
    return files


def _networks(root, files, engine="FSL", **values):
    result = _rs_result(root, engine=engine, **values)
    return _by_name(_check_fmri_resting_networks(result, files, _RS_TRUTH))


def test_resting_networks_each_found_in_its_own_component_pass(tmp_path):
    root = str(tmp_path)
    # A broad noise component in between, then the two networks.
    files = _rs_maps(root, _rs_blob(-5, 0, 5), _rs_blob(-20), _rs_blob(20, value=-4))
    checks = _networks(root, files)
    assert set(checks) == {
        "fmri.rs.network.precentral",
        "fmri.rs.network.rs_posterior",
    }
    assert all(c.passed for c in checks.values()), checks


def test_resting_networks_fused_in_one_component_fail(tmp_path):
    root = str(tmp_path)
    files = _rs_maps(root, _rs_blob(20, -20))
    checks = _networks(root, files)
    assert not checks["fmri.rs.network.precentral"].passed
    assert not checks["fmri.rs.network.rs_posterior"].passed


def test_resting_network_found_twice_does_not_cover_the_other(tmp_path):
    # Two components on the motor network: the posterior one is still missing.
    root = str(tmp_path)
    files = _rs_maps(root, _rs_blob(20), _rs_blob(19))
    checks = _networks(root, files)
    assert checks["fmri.rs.network.precentral"].passed
    assert not checks["fmri.rs.network.rs_posterior"].passed


def test_resting_networks_are_checked_whatever_the_task_fmri_engine(tmp_path):
    # Resting state always runs on FSL: the (task) fmri_engine is irrelevant.
    root = str(tmp_path)
    files = _rs_maps(root, _rs_blob(20, -20))
    checks = _networks(root, files, engine="NILEARN")
    assert not checks["fmri.rs.network.precentral"].passed


def test_resting_networks_skip_a_fixed_dimensionality(tmp_path):
    # ic_dim > 0 deliberately over-splits the two-network phantom.
    root = str(tmp_path)
    files = _rs_maps(root, _rs_blob(20, -20))
    assert _networks(root, files, ic_dim="20") == {}


def test_dipy_bundle_recovery_reads_the_sidecar_not_its_existence(tmp_path):
    dti = _dti_results_dir(str(tmp_path))
    for side in ("lh", "rh"):
        open(os.path.join(dti, "r-%s_%s.vtp" % (SWEEP_TRACT, side)), "w").close()
    # A confident sidecar is not a flag; an unreadable one is.
    with open(os.path.join(dti, "r-%s_lh.conf.json" % SWEEP_TRACT), "w") as f:
        json.dump({"low_confidence": False}, f)
    with open(os.path.join(dti, "r-%s_rh.conf.json" % SWEEP_TRACT), "w") as f:
        f.write("{not json")

    checks = _by_name(_check_dipy_bundle_recovery(_dipy_result(str(tmp_path)), []))

    assert checks["dipy.confidence.%s_lh" % SWEEP_TRACT].passed
    assert not checks["dipy.confidence.%s_rh" % SWEEP_TRACT].passed


def test_results_in_a_mapnode_subfolder_fail(tmp_path):
    """Task fMRI cluster maps left in the MapNode folder are invisible to the
    Slicer scene loader, which lists only results/fMRI."""
    root = tmp_path / RESULTS_DIR
    flat = root / "fMRI" / "r-fmri_0_cluster_a_threshold3.1.nii.gz"
    nested = root / "fMRI" / "_fmri_0_cluster_t3_1_to_ref_ants_apply0" / "r-x.nii.gz"
    for path in (flat, nested):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    ok = _check_no_mapnode_subfolder(str(tmp_path), [str(flat)])
    assert ok.passed
    bad = _check_no_mapnode_subfolder(str(tmp_path), [str(flat), str(nested)])
    assert not bad.passed
    assert "_fmri_0_cluster_t3_1_to_ref_ants_apply0" in bad.detail
