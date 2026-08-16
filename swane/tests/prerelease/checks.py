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
import re
from dataclasses import dataclass, field

import numpy as np

from swane.utils.DataInputList import DataInputList as DIL, FMRI_NUM

#: Severity levels. Only ``error`` makes a pass fail.
ERROR = "error"
WARNING = "warning"
INFO = "info"

RESULTS_DIR = "results"

#: A feature (veins, electrodes, high-FA corridor) must land within this
#: distance of the structure the phantom actually drew. Calibrated against a
#: real run: measured margins are the reference brain at 8.1 mm, the CST at
#: 3.1 mm and the venous sinus at 1.6 mm, so 15 mm leaves headroom for
#: cross-machine variation without masking a gross mislocalisation.
FEATURE_TOLERANCE_MM = 15.0


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = ERROR

    def __post_init__(self):
        # Checks often derive ``passed`` from numpy comparisons, which yield a
        # numpy.bool_ that the JSON report cannot serialise. Normalise to a
        # plain Python bool at the source.
        self.passed = bool(self.passed)

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
    # SWANe names the 3D FLAIR result after its output_name "flair"
    # (r-flair.nii.gz), not "flair3d"; the trailing-digit guard in the matcher
    # keeps it from also claiming the 2D "flair2d_*" results.
    DIL.FLAIR3D: ("flair",),
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

#: Inputs whose resampled-series result is named after an output name that
#: differs from the workflow name (used by the registration check).
_REGISTERED_SERIES_NAME = {
    DIL.FLAIR3D: "flair",
}

#: Inputs that only partially cover the brain, for which a centre-of-mass
#: comparison against the whole-brain reference centre is not meaningful.
_PARTIAL_COVERAGE = {
    DIL.T2_COR,
}

#: Inputs whose results are statistical maps (fMRI activation clusters, ICA
#: z-stats), not a resampled anatomical series, so the series-alignment checks
#: (centre-of-mass, brain overlap) do not apply: the centre of mass of a sparse
#: cluster map is meaningless. Their success is judged by _check_fmri_activation.
_ACTIVATION_ONLY = {DIL["FMRI_%d" % i] for i in range(FMRI_NUM)} | {DIL.FMRI_RS}


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
            (
                "%d result image(s)" % len(files)
                if files
                else "the results folder is empty"
            ),
        )
    )
    if not files:
        return checks

    checks.extend(_check_expected_outputs(result, files))
    checks.extend(_check_integrity(files))
    checks.extend(_check_fmri_activation(result, files))
    checks.extend(_check_reference(result, files))
    checks.extend(_check_nonlinear_registration(result))
    checks.extend(_check_nonlinear_target_alignment(result))
    if ground_truth is not None:
        checks.extend(_check_plausibility(result, files, ground_truth))
    return checks


#: Bounds (mm) on the mean magnitude of a non-linear warp's displacement field.
#: FNIRT ref->MNI on the deformed phantom measures ~8 mm mean, which is the
#: fsaverage->MNI152 baseline plus our injected deformation. The window is
#: deliberately wide: it only has to separate a real warp from a degenerate one
#: (~0 mm, a silently-failed FNIRT) or a diverged one (tens of mm).
NONLINEAR_WARP_MIN_MM = 0.5
NONLINEAR_WARP_MAX_MM = 30.0


def _check_nonlinear_registration(result) -> list:
    """Validate the non-linear registration actually produced a real warp.

    The phantom now carries a fixed non-linear deformation from the atlas (see
    ``helpers/phantom/deformation.py``), so any pass that registers the subject
    to MNI or the symmetric template (FLAT1, the asymmetry index, ICA-AROMA)
    must recover a non-trivial warp. DTI tractography no longer runs its own
    MNI<->reference registration: it reuses the same "mni1" warp FLAT1 computes
    (built once by ``MainWorkflow.ensure_mni1_registration``, whenever FLAT1 or
    tractography is requested), so there is nothing tractography-specific to
    check here beyond what the FLAT1/"mni1" case already covers. FNIRT writes
    the forward transform as
    spline coefficients (intent ``fnirt cubic spline coef``); ``invwarp`` writes
    the inverse as a real displacement field (intent ``fnirt disp field``).

    Only some registrations need the inverse: FLAT1 builds it (to carry atlas
    ROIs back into subject space), while the resting-state ICA-AROMA path only
    warps *forward* to MNI and never inverts. So the inverse is optional here;
    what every non-linear registration must have is the forward warp, and the
    inverse — when present — is what we can measure directly (coefficients are
    not a displacement field, so their magnitude is not read here).

    What this deliberately does *not* do is compare the recovered warp against
    the known deformation field voxel-by-voxel: SWANe registers to MNI, not to
    the undeformed phantom, so the recovered warp also carries the (unknown)
    fsaverage-to-MNI152 baseline, which cannot be separated out here. It reads
    only SWANe's own outputs and derives nothing from the FSL atlases.
    """
    forward = glob.glob(
        os.path.join(result.subject_dir, "**", "*_fieldwarp.nii.gz"), recursive=True
    )
    inverse = glob.glob(
        os.path.join(result.subject_dir, "**", "*_fieldwarp_inverse.nii.gz"),
        recursive=True,
    )
    if not forward and not inverse:
        return []  # this pass performs no non-linear registration

    checks = [
        CheckResult(
            "nonlinear.warp_present",
            bool(forward),  # the inverse is optional (AROMA warps forward only)
            "forward warp(s): %d, inverse field(s): %d" % (len(forward), len(inverse)),
        )
    ]

    for path in sorted(inverse):
        try:
            img, data = _load(path)
        except Exception as exc:
            checks.append(
                CheckResult(
                    "nonlinear.warp_field", False, "cannot load %s: %s" % (path, exc)
                )
            )
            continue
        if data.ndim != 4 or data.shape[-1] != 3:
            continue  # not a displacement field
        magnitude = np.linalg.norm(data, axis=-1)
        finite = magnitude[np.isfinite(magnitude)]
        moved = finite[finite > 1e-3]
        mean_mm = float(moved.mean()) if moved.size else 0.0
        max_mm = float(finite.max()) if finite.size else float("inf")
        ok = (
            finite.size == magnitude.size  # no non-finite displacements
            and NONLINEAR_WARP_MIN_MM <= mean_mm
            and max_mm <= NONLINEAR_WARP_MAX_MM
        )
        checks.append(
            CheckResult(
                "nonlinear.warp_nontrivial",
                ok,
                "displacement mean %.2f mm, max %.2f mm" % (mean_mm, max_mm),
            )
        )
    return checks


#: The non-linearly warped subject must resemble its actual registration target
#: this much. Measured against the real MNI152 1mm brain: Dice 0.94, intensity
#: NCC 0.78. The thresholds keep margin for atlas/version differences while
#: still failing a warp that did not really bring the subject onto the target.
NONLINEAR_TARGET_MIN_DICE = 0.85
NONLINEAR_TARGET_MIN_NCC = 0.5


def _registration_target(node_dir: str):
    """The real image a given nonlinear_reg instance registers to, read at run
    time. MNI templates come from ``$FSLDIR``; the symmetric template ships with
    ``swane_supplement`` (not an FSL atlas). Reading them to score the result is
    allowed; we never copy or derive committed images from them.
    """
    if node_dir.startswith("mni1"):
        # Shared by FLAT1 and DTI tractography: both now consume the single
        # "mni1" nonlinear_reg_workflow instance instead of DTI computing its
        # own MNI<->reference registration (dti_preproc no longer has one).
        fsldir = os.environ.get("FSLDIR")
        if fsldir:
            return os.path.join(fsldir, "data/standard/MNI152_T1_1mm_brain.nii.gz")
    elif node_dir.startswith("sym"):
        try:
            import swane_supplement

            return swane_supplement.sym_template
        except Exception:
            return None
    return None


def _check_nonlinear_target_alignment(result) -> list:
    """Score the non-linear registration against its *actual* target.

    The subject-space checks cannot judge the subject->atlas step, so here the
    warped subject (the reference resampled into the target space by SWANe's own
    apply-warp node) is compared with the real target read at run time. High
    overlap and intensity correlation mean the non-linear registration genuinely
    landed the subject on the atlas, not merely that it produced some warp.
    """
    checks = []
    warped_images = glob.glob(
        os.path.join(result.subject_dir, "**", "*_apply_warp", "*warp.nii.gz"),
        recursive=True,
    )
    for path in sorted(warped_images):
        node_dir = os.path.basename(os.path.dirname(path))  # e.g. mni1_apply_warp
        target = _registration_target(node_dir)
        if not target or not os.path.isfile(target):
            continue
        try:
            warped_img, warped = _load(path)
            target_img, tdata = _load(target)
        except Exception:
            continue
        if warped_img.shape != target_img.shape or not np.allclose(
            warped_img.affine, target_img.affine, atol=1e-2
        ):
            continue
        wmask, tmask = warped > 0, tdata > 0
        denom = int(wmask.sum()) + int(tmask.sum())
        if denom == 0:
            continue
        dice = 2.0 * int(np.logical_and(wmask, tmask).sum()) / denom
        ncc = _ncc(warped, tdata, np.logical_and(wmask, tmask))
        label = node_dir.replace("_apply_warp", "")
        checks.append(
            CheckResult(
                "nonlinear.target_alignment.%s" % label,
                dice >= NONLINEAR_TARGET_MIN_DICE and ncc >= NONLINEAR_TARGET_MIN_NCC,
                "aligned to %s: brain Dice %.3f, intensity NCC %.3f"
                % (os.path.basename(target), dice, ncc),
            )
        )
    return checks


def _ncc(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    """Normalised cross-correlation of two volumes over ``mask``."""
    x = a[mask].astype(np.float64)
    y = b[mask].astype(np.float64)
    if x.size < 2:
        return 0.0
    x -= x.mean()
    y -= y.mean()
    denom = np.sqrt(float((x * x).sum()) * float((y * y).sum()))
    return float((x * y).sum() / denom) if denom > 0 else 0.0


def _check_execution(result) -> list:
    checks = [
        CheckResult(
            "execution.no_failed_nodes",
            not result.node_errors,
            (
                "all %d node(s) completed" % result.nodes_completed
                if not result.node_errors
                else "; ".join(
                    "%s (%s)" % (e["node"], e.get("crash_file") or "no crash file")
                    for e in result.node_errors[:5]
                )
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


def _hint_matches(hint: str, name: str) -> bool:
    """True if ``hint`` occurs in ``name`` but not as the prefix of a longer,
    digit-suffixed token.

    SWANe distinguishes some inputs only by a trailing number in the output
    name (``flair`` vs ``flair2d``), so a bare substring test would let the 3D
    FLAIR hint also claim the 2D results. Refusing a match when a digit follows
    separates the two while still allowing plural/compound names (``vein`` in
    ``veins``, ``cluster`` in ``cluster_task_a``).
    """
    return re.search(re.escape(hint) + r"(?![0-9])", name) is not None


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
        found = [n for n in names if any(_hint_matches(h, n) for h in hints)]
        checks.append(
            CheckResult(
                "output.%s" % input_name,
                bool(found),
                found[0] if found else "no result matching %s" % "/".join(hints),
            )
        )
    return checks


def _is_activation_map(name: str) -> bool:
    """True for fMRI cluster maps and ICA z-stat maps (thresholded outputs)."""
    lowered = name.lower()
    return "cluster" in lowered or "zstat" in lowered


def _check_fmri_activation(result, files: list) -> list:
    """Confirm the fMRI workflows actually produced activation.

    Thresholding legitimately empties some maps (a high z, or a contrast with no
    real effect), so the integrity layer does not fail on an empty cluster map.
    This positive check makes sure at least *one* map is non-empty per fMRI
    input, i.e. the pipeline found signal rather than silently producing nothing.
    """
    checks = []
    names_lower = {os.path.basename(f).lower(): f for f in files}
    for input_name in result.inputs:
        try:
            data_input = DIL[input_name.upper()]
        except KeyError:
            continue
        if data_input not in _ACTIVATION_ONLY:
            continue
        if data_input is DIL.FMRI_RS:
            token, label = "zstat", "ICA z-stat"
        else:
            token, label = "%s_cluster" % input_name.lower(), "activation cluster"
        maps = [p for n, p in names_lower.items() if token in n]
        if not maps:
            continue
        nonempty = []
        for path in maps:
            try:
                _, data = _load(path)
            except Exception:
                continue
            if int((data != 0).sum()) > 0:
                nonempty.append(os.path.basename(path))
        checks.append(
            CheckResult(
                "fmri.activation.%s" % input_name,
                bool(nonempty),
                (
                    "%d of %d %s map(s) non-empty" % (len(nonempty), len(maps), label)
                    if nonempty
                    else "every %s map is empty" % label
                ),
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
            checks.append(CheckResult("integrity.%s" % name, False, "no finite voxel"))
            continue
        values = data[finite]
        nonfinite_fraction = 1.0 - finite.mean()
        spread = float(values.max() - values.min())
        problems = []
        if nonfinite_fraction > 0.01:
            problems.append("%.1f%% non-finite" % (100 * nonfinite_fraction))
        if spread <= 0:
            # An all-zero thresholded activation/cluster map is a valid
            # statistical result (no voxel survived the threshold), not a broken
            # output. Only flag a constant image for everything else.
            if not (_is_activation_map(name) and float(values.min()) == 0.0):
                problems.append("constant image (all %g)" % float(values.min()))
        checks.append(
            CheckResult(
                "integrity.%s" % name,
                not problems,
                (
                    "; ".join(problems)
                    if problems
                    else "range [%.4g, %.4g]" % (values.min(), values.max())
                ),
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
            (
                "all registered results on the reference grid"
                if not off_grid
                else "not on the reference grid: %s" % ", ".join(sorted(off_grid)[:5])
            ),
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

    checks.extend(_check_registration(result, files, centre))
    checks.extend(_check_fa(files, truth))
    checks.extend(_check_feature(files, truth, "veins", "venous_sinus"))
    return checks


def _converted_image(subject_dir: str, workflow_name: str):
    """The series as dcm2niix produced it, before any registration.

    Lives in the workflow working directory under ``<input>/<input>_conv/``.
    """
    pattern = os.path.join(subject_dir, "**", workflow_name, "*conv*", "*.nii.gz")
    hits = [h for h in glob.glob(pattern, recursive=True) if os.path.isfile(h)]
    return sorted(hits, key=len)[0] if hits else None


def _check_registration(result, files: list, reference_centre) -> list:
    """Verify the registration tools really realigned the deliberately posed series.

    The phantom displaces every series except the reference by a few
    millimetres and degrees, on an otherwise clean scanner grid — the content
    moves, the header does not, so header-based alignment cannot fake it and
    FLIRT/FNIRT/SynthMorph have genuine work to do.

    Judging the registered result against the reference *alone* is weak,
    because two different modalities never share a centre of mass exactly. So
    the comparison is made **before and after**: the same series, same
    modality, measured against the same reference. The modality bias cancels,
    and what remains is whether registration moved the content closer. A
    registration that silently did nothing leaves the offset untouched.
    """
    checks = []
    if reference_centre is None or not result.subject_dir:
        return checks

    names = {os.path.basename(f).lower(): f for f in files}
    for input_name in result.inputs:
        try:
            data_input = DIL[input_name.upper()]
        except KeyError:
            continue
        if data_input is DIL.T13D:
            continue  # the reference itself is not posed and not registered
        if data_input in _ACTIVATION_ONLY:
            # fMRI produces activation maps, not a resampled series; the centre
            # of mass of a sparse cluster map does not measure registration.
            continue
        if data_input in _PARTIAL_COVERAGE:
            # A partially-covered series (coronal T2 over the temporal lobes)
            # has a centre of mass several mm from the whole-brain centre by
            # construction, and that offset dwarfs the ~1 mm pose it must
            # recover, so before/after against the whole-brain centre cannot
            # tell a good registration from a bad one. Skip rather than warn.
            continue

        # Only the *series itself*, resampled into reference space, can be
        # compared with its own pre-registration image. Derived maps (the vein
        # score, FA, cluster z-stats) hold different content, so a before/after
        # centre-of-mass comparison against them would be meaningless -- the
        # modality bias no longer cancels because the two images are not the
        # same thing.
        workflow_name = str(data_input.value.workflow_name)
        # The resampled series is named after the workflow's *output name*, which
        # usually equals the workflow name but not always (3D FLAIR is written
        # as r-flair, not r-flair3d). The digit guard stops "flair" from also
        # matching the 2D "r-flair2d_*" results.
        core = _REGISTERED_SERIES_NAME.get(data_input, workflow_name).lower()
        candidates = [
            path
            for name, path in names.items()
            if name.startswith("r-" + core) and _hint_matches(core, name)
        ]
        if not candidates:
            continue
        # Prefer the plain series (r-<core>.nii.gz) over the _brain variant.
        registered = min(candidates, key=lambda p: len(os.path.basename(p)))

        converted = _converted_image(result.subject_dir, workflow_name)
        if converted is None:
            continue

        try:
            post_img, post_data = _load(registered)
            pre_img, pre_data = _load(converted)
        except Exception:
            continue

        post = _centre_of_mass_ras(np.clip(post_data, 0, None), post_img.affine)
        pre = _centre_of_mass_ras(np.clip(pre_data, 0, None), pre_img.affine)
        if post is None or pre is None:
            continue

        before = float(np.linalg.norm(pre - reference_centre))
        after = float(np.linalg.norm(post - reference_centre))
        checks.append(
            CheckResult(
                "registration.%s" % input_name,
                after <= before + 0.25,  # a small tolerance for interpolation
                "centre-of-mass offset from the reference: %.2f mm before, "
                "%.2f mm after registration" % (before, after),
            )
        )

        # Goodness, not just improvement: the registered brain must actually
        # overlap the reference brain. Both are the *same* subject in the *same*
        # (reference) space -- this is a subject-space, atlas-free comparison --
        # so a correct linear registration makes the masks coincide. Dice falls
        # off sharply under a gross misregistration. A few percent below 1 is
        # expected from cross-modality skull-strip differences and interpolation.
        overlap = _brain_overlap(names, core)
        if overlap is not None:
            checks.append(
                CheckResult(
                    "registration.overlap.%s" % input_name,
                    overlap >= REGISTRATION_MIN_DICE,
                    "brain Dice with the reference: %.3f" % overlap,
                )
            )
    return checks


#: A registered series' brain must overlap the reference brain at least this
#: much (Dice). Measured 0.97 for the 3D/2D FLAIR and MDC series; 0.90 leaves
#: room for cross-modality skull-strip differences while still failing a gross
#: misregistration (a 5 mm shift drops a brain-sized mask well below this).
REGISTRATION_MIN_DICE = 0.90


def _brain_overlap(names: dict, core: str):
    """Dice between the registered series brain and the reference brain.

    Both live in reference space on the same grid, so the masks are directly
    comparable. Returns ``None`` if either brain image is missing or the grids
    do not match.
    """
    ref = names.get("ref_brain.nii.gz")
    brain = next(
        (
            path
            for name, path in names.items()
            if name.startswith("r-" + core)
            and name.endswith("_brain.nii.gz")
            and _hint_matches(core, name)
        ),
        None,
    )
    if ref is None or brain is None:
        return None
    try:
        ref_img, ref_data = _load(ref)
        brain_img, brain_data = _load(brain)
    except Exception:
        return None
    if ref_img.shape != brain_img.shape or not np.allclose(
        ref_img.affine, brain_img.affine, atol=1e-2
    ):
        return None
    a, b = ref_data > 0, brain_data > 0
    denom = int(a.sum()) + int(b.sum())
    if denom == 0:
        return None
    return 2.0 * int(np.logical_and(a, b).sum()) / denom


def _check_fa(files: list, truth: GroundTruth) -> list:
    """FA must be in range, and anisotropy must concentrate in the CST."""
    checks = []
    for path in files:
        # Drop the extension before tokenising: "r-FA.nii.gz" -> ["r", "fa"],
        # otherwise the token is "fa.nii.gz" and the FA result is never matched.
        stem = os.path.basename(path).lower().split(".")[0]
        if "fa" not in stem.replace("-", "_").split("_"):
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


def _fields(check) -> tuple:
    """Read ``(passed, severity)`` from a check, live object or reloaded dict.

    Results read back from a previous run arrive as plain dicts, so counting
    must not assume attribute access.
    """
    if isinstance(check, dict):
        return bool(check.get("passed")), check.get("severity", ERROR)
    return bool(check.passed), check.severity


def summarise(checks: list) -> tuple:
    """Return ``(passed, failed_errors, failed_warnings)`` counts."""
    passed = errors = warnings = 0
    for check in checks:
        ok, severity = _fields(check)
        if ok:
            passed += 1
        elif severity == WARNING:
            warnings += 1
        else:
            errors += 1
    return passed, errors, warnings
