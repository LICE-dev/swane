"""Unit coverage for the pure-logic parts of :mod:`swane.tests.prerelease.checks`.

These run without the phantom or the pipeline: they build a subject directory
by hand and feed a synthetic :class:`PassResult` to a single check, asserting
it reads the *real* on-disk layout the workflow produces. The dipy bundle check
is here specifically because it once looked in the wrong directory for the wrong
filenames and so silently emitted no checks -- a green pass that validated
nothing. A directory-shape regression must fail loudly instead of vanishing.
"""

import os

from swane.tests.prerelease.checks import _check_dipy_bundle_recovery, RESULTS_DIR
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
    # DipyBundleRecovery writes this sidecar only for a low-confidence bundle.
    open(os.path.join(dti, "r-%s_rh.lowconf.json" % SWEEP_TRACT), "w").close()

    checks = _by_name(_check_dipy_bundle_recovery(_dipy_result(str(tmp_path)), []))

    # The bundle still exists (recovery passes) but is flagged (confidence fails).
    assert checks["dipy.recovery.%s_rh" % SWEEP_TRACT].passed
    assert checks["dipy.confidence.%s_lh" % SWEEP_TRACT].passed
    assert not checks["dipy.confidence.%s_rh" % SWEEP_TRACT].passed
