"""Unit coverage for the pure-logic parts of :mod:`swane.tests.prerelease.checks`.

These run without the phantom or the pipeline: they build a subject directory
by hand and feed a synthetic :class:`PassResult` to a single check, asserting
it reads the *real* on-disk layout the workflow produces. The dipy bundle check
is here specifically because it once looked in the wrong directory for the wrong
filenames and so silently emitted no checks -- a green pass that validated
nothing. A directory-shape regression must fail loudly instead of vanishing.
"""

import os

from types import SimpleNamespace

import nibabel as nib
import numpy as np
from nipype.utils.filemanip import savepkl

from swane.tests.prerelease.checks import (
    _check_dipy_bundle_recovery,
    _check_fmri_activation,
    NILEARN_TASK_EXPECTED_VOXELS,
    _check_nilearn_resting,
    NILEARN_RS_EXPECTED_COMPONENTS,
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
    # DipyBundleRecovery writes this sidecar only for a low-confidence bundle.
    open(os.path.join(dti, "r-%s_rh.lowconf.json" % SWEEP_TRACT), "w").close()

    checks = _by_name(_check_dipy_bundle_recovery(_dipy_result(str(tmp_path)), []))

    # The bundle still exists (recovery passes) but is flagged (confidence fails).
    assert checks["dipy.recovery.%s_rh" % SWEEP_TRACT].passed
    assert checks["dipy.confidence.%s_lh" % SWEEP_TRACT].passed
    assert not checks["dipy.confidence.%s_rh" % SWEEP_TRACT].passed
    # A flagged bundle is a warning, not a broken pass: the recovery mechanism
    # is doing its job (see _check_dipy_bundle_recovery's docstring).
    assert checks["dipy.confidence.%s_rh" % SWEEP_TRACT].severity == WARNING


# --------------------------------------------------------------------------- #
# NILEARN resting-state checks
# --------------------------------------------------------------------------- #
def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.float32), np.eye(4)), path)


def _rs_result(subject_dir, engine="NILEARN", **values):
    return PassResult(
        name="fmri_task_and_rest",
        subject_dir=subject_dir,
        inputs=["t13d", "fmri_resting_state"],
        values={"fmri_engine": engine, **values},
    )


def _rs_layout(
    root,
    n_components=NILEARN_RS_EXPECTED_COMPONENTS,
    ica_node="ica_fastica_icasso",
    k=12,
    maps_nonempty=True,
):
    """Build the on-disk layout of a NILEARN resting-state run: the final ICA
    and the cluster-extent report in the Nipype work dir, the registered maps
    in the results folder. Returns the result image list."""
    wf = os.path.join(root, "prerelease_wf", "fMRI_resting_state")
    _save(os.path.join(wf, ica_node, "ica_IC.nii.gz"), np.ones((4, 4, 4, n_components)))
    # The AROMA-pass CanICA writes a file with the same name: never the source.
    _save(
        os.path.join(wf, "preproc_ica_canica", "ica_IC.nii.gz"), np.ones((4, 4, 4, 7))
    )
    if k is not None:
        # Nipype removes the unconsumed JSON report (remove_unnecessary_outputs);
        # the node's result file keeps k.
        node_dir = os.path.join(wf, "ica_cluster_extent")
        os.makedirs(node_dir, exist_ok=True)
        savepkl(
            os.path.join(node_dir, "result_ica_cluster_extent.pklz"),
            SimpleNamespace(outputs=SimpleNamespace(min_cluster_voxels=k)),
        )
    files = []
    for idx in range(1, n_components + 1):
        data = np.zeros((4, 4, 4))
        if maps_nonempty and idx == 1:
            data[1, 1, 1] = 3.0
        path = os.path.join(
            root, RESULTS_DIR, "fMRI_resting_state", "r-thresh_zstat%02d.nii.gz" % idx
        )
        _save(path, data)
        files.append(path)
    return files


def test_nilearn_resting_checks_pass_on_the_workflow_layout(tmp_path):
    files = _rs_layout(str(tmp_path))
    checks = _by_name(_check_nilearn_resting(_rs_result(str(tmp_path)), files))
    assert set(checks) == {
        "fmri.rs.ica_source",
        "fmri.determinism.rs_components",
        "fmri.rs.cluster_extent",
        "fmri.rs.zstat_maps",
    }
    for check in checks.values():
        assert check.passed, check


def test_nilearn_resting_checks_skip_the_fsl_engine(tmp_path):
    files = _rs_layout(str(tmp_path))
    assert _check_nilearn_resting(_rs_result(str(tmp_path), engine="FSL"), files) == []


def test_nilearn_resting_component_count_ignores_the_aroma_pass_ica(tmp_path):
    # Only the AROMA-pass CanICA output exists: the final ICA is missing, and
    # its 7 components must not be taken for the final count.
    files = _rs_layout(str(tmp_path), ica_node="some_other_node")
    checks = _by_name(_check_nilearn_resting(_rs_result(str(tmp_path)), files))
    assert not checks["fmri.rs.ica_source"].passed
    assert not checks["fmri.determinism.rs_components"].passed


def test_nilearn_resting_component_count_mismatch_fails(tmp_path):
    files = _rs_layout(str(tmp_path), n_components=NILEARN_RS_EXPECTED_COMPONENTS + 1)
    checks = _by_name(_check_nilearn_resting(_rs_result(str(tmp_path)), files))
    assert checks["fmri.rs.ica_source"].passed
    assert not checks["fmri.determinism.rs_components"].passed


def test_nilearn_resting_fixed_ic_dim_expects_that_many_components(tmp_path):
    # Without FSL, fmri_alt_settings downgrades to NILEARN but keeps ic_dim=20:
    # the fixed dimensionality, not the estimated phantom count, is expected.
    files = _rs_layout(str(tmp_path), n_components=20)
    checks = _by_name(
        _check_nilearn_resting(_rs_result(str(tmp_path), ic_dim="20"), files)
    )
    assert checks["fmri.determinism.rs_components"].passed


def test_nilearn_resting_fixed_ic_dim_mismatch_fails(tmp_path):
    files = _rs_layout(str(tmp_path), n_components=NILEARN_RS_EXPECTED_COMPONENTS)
    checks = _by_name(
        _check_nilearn_resting(_rs_result(str(tmp_path), ic_dim="20"), files)
    )
    assert not checks["fmri.determinism.rs_components"].passed


def test_nilearn_resting_cluster_extent_report_missing_or_zero_fails(tmp_path):
    missing = tmp_path / "missing"
    files = _rs_layout(str(missing), k=None)
    checks = _by_name(_check_nilearn_resting(_rs_result(str(missing)), files))
    assert not checks["fmri.rs.cluster_extent"].passed

    zero = tmp_path / "zero"
    files = _rs_layout(str(zero), k=0)
    checks = _by_name(_check_nilearn_resting(_rs_result(str(zero)), files))
    assert not checks["fmri.rs.cluster_extent"].passed


def test_nilearn_resting_all_empty_maps_fail(tmp_path):
    files = _rs_layout(str(tmp_path), maps_nonempty=False)
    checks = _by_name(_check_nilearn_resting(_rs_result(str(tmp_path)), files))
    assert not checks["fmri.rs.zstat_maps"].passed


def _task_result(subject_dir, registration="FSL", deskull="BET"):
    return PassResult(
        name="fmri_task_and_rest",
        subject_dir=subject_dir,
        inputs=["t13d", "fmri_0"],
        values={
            "fmri_engine": "NILEARN",
            "registration_engine": registration,
            "deskull_engine": deskull,
        },
    )


def _task_maps(root, offset=0):
    """Cluster maps of fmri_0 with the expected voxel counts (+ offset)."""
    files = []
    for name, count in NILEARN_TASK_EXPECTED_VOXELS["fmri_0"].items():
        data = np.zeros(64 * 64 * 16, dtype=np.float32)
        data[: count + offset] = 1.0
        path = os.path.join(root, RESULTS_DIR, "fMRI_0", name)
        _save(path, data.reshape(64, 64, 16))
        files.append(path)
    return files


def _determinism(checks):
    return {n: c for n, c in _by_name(checks).items() if "determinism" in n}


def test_task_voxel_counts_pass_on_the_pinned_configuration(tmp_path):
    files = _task_maps(str(tmp_path))
    checks = _determinism(_check_fmri_activation(_task_result(str(tmp_path)), files))
    assert set(checks) == {
        "fmri.determinism.fmri_0_3",
        "fmri.determinism.fmri_0_5",
        "fmri.determinism.fmri_0_7",
    }
    for check in checks.values():
        assert check.passed, check


def test_task_voxel_counts_mismatch_fails(tmp_path):
    files = _task_maps(str(tmp_path), offset=1)
    checks = _determinism(_check_fmri_activation(_task_result(str(tmp_path)), files))
    assert checks and not any(c.passed for c in checks.values())


def test_task_voxel_counts_skip_other_registrations(tmp_path):
    # The counts depend on the func->ref registration: they are pinned only for
    # the configuration they were obtained with.
    files = _task_maps(str(tmp_path))
    result = _task_result(str(tmp_path), registration="ANTS", deskull="ANTSPYNET")
    assert _determinism(_check_fmri_activation(result, files)) == {}
