"""Decide whether a pass actually succeeded.

"The workflow finished" is a weak claim: a registration can silently leave the
series where it started, a skull strip can return the whole head, a tensor fit
can produce a field of NaN, and every one of those still writes an output file
and exits zero. So the checks come in three layers:

1. **execution** - no node failed, no crash file, the expected results exist;
2. **integrity** - each result is a loadable, finite, non-degenerate image on
   the reference grid where it should be;
3. **plausibility** - the result matches what we *know* is in the phantom.

Layer 3 is only possible because we generate the data ourselves: the phantom's
tissue model carries the motor cortex, the corticospinal corridor and the
venous sinuses as explicit masks, and every series except the reference was
displaced by a known pose on an otherwise clean grid. Comparing against that is
both a real test and licence-clean — nothing here reads an FSL or XTRACT atlas,
and no FSL code is reused. The tools are run and their output inspected, which
is all their licences allow.

Comparisons are done in RAS world coordinates (centre of mass in millimetres),
so a result never has to be resampled onto the ground truth to be judged.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import numpy as np

from swane.utils.DataInputList import DataInputList as DIL

#: Severity levels. Only ``error`` makes a pass fail.
ERROR = "error"
WARNING = "warning"
INFO = "info"

RESULTS_DIR = "results"

#: How far the centre of mass of a registered series may sit from the
#: reference, in millimetres. The phantom's inter-series poses are a few mm, so
#: a registration that did nothing at all lands well outside this.
REGISTRATION_TOLERANCE_MM = 2.5

#: A feature (veins, electrodes) must land within this distance of the
#: structure the phantom actually drew.
FEATURE_TOLERANCE_MM = 15.0


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = ERROR

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "severity": self.severity,
        }

    def __str__(self) -> str:
        mark = "PASS" if self.passed else self.severity.upper()
        return "    [%-7s] %-38s %s" % (mark, self.name, self.detail)


@dataclass
class GroundTruth:
    """Phantom anatomy in RAS millimetres, used as the reference for layer 3."""

    centres: dict = field(default_factory=dict)  # feature -> (x, y, z) in RAS mm

    @classmethod
    def build(cls, freesurfer_home: str = None) -> "GroundTruth":
        from swane.tests.helpers.phantom.tissue import (
            TissueClass as TC,
            build_tissue_model,
        )

        model = build_tissue_model(freesurfer_home)
        centres = {}
        for name, mask in (
            ("brain", np.isin(model.labels, [TC.CORTICAL_GM, TC.DEEP_GM, TC.WM])),
            ("precentral", model.precentral),
            ("cst", model.cst),
            ("venous_sinus", model.labels == TC.VENOUS_SINUS),
        ):
            centre = _centre_of_mass_ras(np.asarray(mask, dtype=float), model.affine)
            if centre is not None:
                centres[name] = centre
        return cls(centres=centres)


def _centre_of_mass_ras(weights: np.ndarray, affine: np.ndarray):
    """Intensity-weighted centre of mass, in RAS millimetres."""
    total = float(weights.sum())
    if not np.isfinite(total) or total <= 0:
        return None
    grid = np.indices(weights.shape, dtype=float)
    voxel = np.array([float((grid[i] * weights).sum()) / total for i in range(3)])
    return affine[:3, :3].dot(voxel) + affine[:3, 3]


def _load(path: str):
    import nibabel as nib

    img = nib.load(path)
    return img, np.asanyarray(img.dataobj, dtype=np.float32)


def _results_root(subject_dir: str) -> str:
    return os.path.join(subject_dir, RESULTS_DIR)


def _find_results(subject_dir: str) -> list:
    root = _results_root(subject_dir)
    if not os.path.isdir(root):
        return []
    found = []
    for pattern in ("*.nii.gz", "*.nii", "*.mgz"):
        found.extend(glob.glob(os.path.join(root, "**", pattern), recursive=True))
    return sorted(found)


#: Per input, a substring that must appear in at least one result file name.
#: Kept loose on purpose: the exact names come from the node output filenames,
#: and the point is to catch "this input produced nothing at all".
EXPECTED_RESULT_HINTS = {
    DIL.T13D: ("ref",),
    DIL.FLAIR3D: ("flair3d",),
    DIL.MDC: ("mdc",),
    DIL.T2_COR: ("t2_cor",),
    DIL.FLAIR2D_TRA: ("flair2d",),
    DIL.FLAIR2D_COR: ("flair2d",),
    DIL.FLAIR2D_SAG: ("flair2d",),
    DIL.ASL: ("asl",),
    DIL.PET: ("pet",),
    DIL.VENOUS_MR: ("vein", "venous"),
    DIL.VENOUS_CT: ("vein", "venous"),
    DIL.SEEG_CT: ("electrode", "seeg"),
    DIL.DTI: ("fa",),
    DIL.FMRI_0: ("fmri_0", "cluster"),
    DIL.FMRI_1: ("fmri_1", "cluster"),
    DIL.FMRI_RS: ("zstat", "resting"),
}


def check_pass(result, ground_truth: GroundTruth = None) -> list:
    """Run every applicable check against a finished pass."""
    checks = []
    if result.status == "skipped":
        return checks

    checks.extend(_check_execution(result))
    if not result.subject_dir or not os.path.isdir(result.subject_dir):
        checks.append(
            CheckResult("results.present", False, "no subject folder was produced")
        )
        return checks

    files = _find_results(result.subject_dir)
    checks.append(
        CheckResult(
            "results.present",
            bool(files),
            "%d result image(s)" % len(files)
            if files
            else "the results folder is empty",
        )
    )
    if not files:
        return checks

    checks.extend(_check_expected_outputs(result, files))
    checks.extend(_check_integrity(files))
    checks.extend(_check_reference(result, files))
    if ground_truth is not None:
        checks.extend(_check_plausibility(result, files, ground_truth))
    return checks


def _check_execution(result) -> list:
    checks = [
        CheckResult(
            "execution.no_failed_nodes",
            not result.node_errors,
            "all %d node(s) completed" % result.nodes_completed
            if not result.node_errors
            else "; ".join(
                "%s (%s)" % (e["node"], e.get("crash_file") or "no crash file")
                for e in result.node_errors[:5]
            ),
        ),
        CheckResult(
            "execution.completed",
            result.status == "completed",
            result.reason or result.status,
        ),
    ]
    if result.insufficient_resources:
        checks.append(
            CheckResult(
                "execution.resources",
                False,
                "a node was refused for lack of RAM; raise --ram",
                severity=WARNING,
            )
        )
    return checks


def _check_expected_outputs(result, files: list) -> list:
    """Every loaded input must contribute at least one result."""
    names = [os.path.basename(f).lower() for f in files]
    checks = []
    for input_name in result.inputs:
        try:
            data_input = DIL[input_name.upper()]
        except KeyError:
            continue
        hints = EXPECTED_RESULT_HINTS.get(data_input)
        if not hints:
            continue
        found = [n for n in names if any(h in n for h in hints)]
        checks.append(
            CheckResult(
                "output.%s" % input_name,
                bool(found),
                found[0] if found else "no result matching %s" % "/".join(hints),
            )
        )
    return checks


def _check_integrity(files: list) -> list:
    """Each result must be a loadable, finite, non-constant image."""
    checks = []
    for path in files:
        name = os.path.basename(path)
        try:
            _, data = _load(path)
        except Exception as exc:  # unreadable output is a hard failure
            checks.append(
                CheckResult("integrity.%s" % name, False, "cannot load: %s" % exc)
            )
            continue

        finite = np.isfinite(data)
        if not finite.any():
            checks.append(
                CheckResult("integrity.%s" % name, False, "no finite voxel")
            )
            continue
        values = data[finite]
        nonfinite_fraction = 1.0 - finite.mean()
        spread = float(values.max() - values.min())
        problems = []
        if nonfinite_fraction > 0.01:
            problems.append("%.1f%% non-finite" % (100 * nonfinite_fraction))
        if spread <= 0:
            problems.append("constant image (all %g)" % float(values.min()))
        checks.append(
            CheckResult(
                "integrity.%s" % name,
                not problems,
                "; ".join(problems)
                if problems
                else "range [%.4g, %.4g]" % (values.min(), values.max()),
            )
        )
    return checks


def _reference_image(files: list):
    """The skull-stripped reference, which every other result registers to."""
    for path in files:
        if os.path.basename(path).lower().startswith("ref_brain"):
            return path
    for path in files:
        if os.path.basename(path).lower().startswith("ref"):
            return path
    return None


def _check_reference(result, files: list) -> list:
    """The reference must be a plausible brain, and registered results share its grid."""
    import nibabel as nib

    checks = []
    reference = _reference_image(files)
    if reference is None:
        return [
            CheckResult(
                "reference.present", False, "no reference image among the results"
            )
        ]

    ref_img, ref_data = _load(reference)
    brain_voxels = int((ref_data > 0).sum())
    checks.append(
        CheckResult(
            "reference.brain_not_empty",
            brain_voxels > 1000,
            "%d non-zero voxel(s)" % brain_voxels,
        )
    )
    # A skull strip that returned the whole field of view has done nothing.
    filled = brain_voxels / float(ref_data.size)
    checks.append(
        CheckResult(
            "reference.skull_removed",
            filled < 0.75,
            "brain fills %.0f%% of the field of view" % (100 * filled),
        )
    )

    # Registered results are resampled into reference space: same grid.
    off_grid = []
    for path in files:
        name = os.path.basename(path)
        if not name.lower().startswith("r-"):
            continue
        try:
            img = nib.load(path)
        except Exception:
            continue
        if img.shape[:3] != ref_img.shape[:3] or not np.allclose(
            img.affine, ref_img.affine, atol=1e-3
        ):
            off_grid.append(name)
    checks.append(
        CheckResult(
            "reference.registered_share_grid",
            not off_grid,
            "all registered results on the reference grid"
            if not off_grid
            else "not on the reference grid: %s" % ", ".join(sorted(off_grid)[:5]),
        )
    )
    return checks


def _check_plausibility(result, files: list, truth: GroundTruth) -> list:
    """Compare results against the anatomy the phantom actually drew."""
    checks = []
    reference = _reference_image(files)
    if reference is None or "brain" not in truth.centres:
        return checks

    # --- the reference brain must sit where the phantom's brain is ----------
    ref_img, ref_data = _load(reference)
    centre = _centre_of_mass_ras(np.clip(ref_data, 0, None), ref_img.affine)
    if centre is not None:
        distance = float(np.linalg.norm(centre - truth.centres["brain"]))
        checks.append(
            CheckResult(
                "plausibility.reference_position",
                distance <= FEATURE_TOLERANCE_MM,
                "reference brain centre is %.1f mm from the phantom's" % distance,
            )
        )

    # --- registration must have removed the known inter-series offset -------
    # Every phantom series except t13d carries a small rigid pose. After
    # registration to the reference the content must line up again; a
    # registration that silently did nothing leaves the original offset.
    for path in files:
        name = os.path.basename(path)
        lowered = name.lower()
        if not lowered.startswith("r-") or "brain" not in lowered:
            continue
        try:
            img, data = _load(path)
        except Exception:
            continue
        moved = _centre_of_mass_ras(np.clip(data, 0, None), img.affine)
        if moved is None or centre is None:
            continue
        distance = float(np.linalg.norm(moved - centre))
        checks.append(
            CheckResult(
                "plausibility.aligned.%s" % name,
                distance <= REGISTRATION_TOLERANCE_MM,
                "%.2f mm from the reference brain centre" % distance,
                severity=WARNING,
            )
        )

    checks.extend(_check_fa(files, truth))
    checks.extend(_check_feature(files, truth, "veins", "venous_sinus"))
    return checks


def _check_fa(files: list, truth: GroundTruth) -> list:
    """FA must be in range, and anisotropy must concentrate in the CST."""
    checks = []
    for path in files:
        if "fa" not in os.path.basename(path).lower().replace("-", "_").split("_"):
            continue
        img, data = _load(path)
        finite = data[np.isfinite(data)]
        if not finite.size:
            continue
        # FA is a ratio: negatives are meaningless and >1 only from noise.
        checks.append(
            CheckResult(
                "dti.fa_range",
                finite.min() >= -1e-3 and finite.max() <= 1.3,
                "FA in [%.3f, %.3f]" % (finite.min(), finite.max()),
            )
        )
        anisotropic = data > 0.4
        count = int(anisotropic.sum())
        checks.append(
            CheckResult(
                "dti.fa_has_anisotropy",
                count > 100,
                "%d voxel(s) with FA > 0.4" % count,
            )
        )
        if count and "cst" in truth.centres:
            centre = _centre_of_mass_ras(anisotropic.astype(float), img.affine)
            if centre is not None:
                distance = float(np.linalg.norm(centre - truth.centres["cst"]))
                checks.append(
                    CheckResult(
                        "dti.anisotropy_in_cst",
                        distance <= FEATURE_TOLERANCE_MM,
                        "high-FA centre is %.1f mm from the phantom CST" % distance,
                        severity=WARNING,
                    )
                )
        break
    return checks


def _check_feature(files: list, truth: GroundTruth, token: str, truth_key: str) -> list:
    """A detected feature must land near the structure the phantom drew."""
    checks = []
    if truth_key not in truth.centres:
        return checks
    for path in files:
        if token not in os.path.basename(path).lower():
            continue
        img, data = _load(path)
        positive = data > (np.nanmax(data) * 0.5 if np.isfinite(data).any() else 0)
        count = int(positive.sum())
        checks.append(
            CheckResult(
                "%s.detected" % token, count > 0, "%d voxel(s) above half-max" % count
            )
        )
        if count:
            centre = _centre_of_mass_ras(positive.astype(float), img.affine)
            if centre is not None:
                distance = float(np.linalg.norm(centre - truth.centres[truth_key]))
                checks.append(
                    CheckResult(
                        "%s.position" % token,
                        distance <= FEATURE_TOLERANCE_MM * 2,
                        "%.1f mm from the phantom %s" % (distance, truth_key),
                        severity=WARNING,
                    )
                )
        break
    return checks


def summarise(checks: list) -> tuple:
    """Return ``(passed, failed_errors, failed_warnings)`` counts."""
    passed = sum(1 for c in checks if c.passed)
    errors = sum(1 for c in checks if not c.passed and c.severity == ERROR)
    warnings = sum(1 for c in checks if not c.passed and c.severity == WARNING)
    return passed, errors, warnings
