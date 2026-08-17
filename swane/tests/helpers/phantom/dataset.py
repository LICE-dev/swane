"""Build (and cache) the complete phantom DICOM subject.

Generating the whole exam costs a couple of minutes, so the result is cached on
disk and reused across runs and across test sessions.  The cache key is a hash
of the generator version, the profile and the fsaverage build, so retuning any
parameter transparently invalidates it.

Typical use from a test::

    from swane.tests.helpers.phantom.dataset import get_phantom_subject
    subject_dir = get_phantom_subject()   # cached after the first call
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass

import numpy as np

from swane.tests.helpers.phantom.catalog import build_catalog
from swane.tests.helpers.phantom.dicom_writer import write_volume_series
from swane.tests.helpers.phantom.sequences import (
    render_bold,
    render_dwi,
    render_structural,
)
from swane.tests.helpers.phantom.tissue import TissueClass as TC, build_tissue_model

#: Bump when the generated data changes in a way tests must notice.
#: v5: anatomy carries a fixed smooth non-linear deformation (deformation.py)
#: so the subject differs non-linearly from the atlas and FNIRT/SynthMorph are
#: exercised, not only the rigid inter-series alignment.
#: v6: CT skull HU raised 1100 -> 1900 (catalog.LUT_CT) so a fixed
#: skull_threshold=1500 (tests/prerelease/plan.py) has real bone to segment.
#: v7: fmri_1 generated with no dummy volumes (catalog), so the sweep can test
#: del_vols=0 on data that genuinely has none instead of faking "no trim" on
#: padded data (which desynced the GLM and emptied the activation maps).
GENERATOR_VERSION = "7"

#: Default cache root; ``SWANE_PHANTOM_DIR`` overrides it.
DEFAULT_CACHE_ROOT = os.path.join(os.path.expanduser("~"), "test_swane", "phantom")

DICOM_DIR_NAME = "dicom"


@dataclass(frozen=True)
class PhantomProfile:
    """Voxel geometry and timing of the phantom exam.

    The single shipped profile is deliberately coarse ("fast"): the goal is to
    keep the FSL/recon-all path quick.  Note the SynthStrip/SynthSeg/SynthMorph
    family re-conforms to 1 mm 256^3 internally, so *their* cost does not depend
    on these numbers.
    """

    name: str = "fast"
    iso_3d_mm: float = 1.5  # 3D T1w / FLAIR / MDC / venous MR
    in_plane_2d_mm: float = 1.5  # 2D FLAIR / T2
    slice_2d_mm: float = 3.0
    dwi_mm: float = 3.0
    dwi_directions: int = 6  # minimum for a tensor fit
    bold_mm: float = 4.0
    bold_tr_s: float = 2.5
    # task and rest blocks have fixed but *different* lengths
    bold_task_s: float = 20.0
    bold_rest_s: float = 30.0
    # dummy volumes to discard at each end (del_start_vols / del_end_vols)
    bold_dummy_start: int = 4
    bold_dummy_end: int = 2
    # rArA: 4 x (rest 30 + task 20) = 200 s -> 80 core vols at TR 2.5 s
    bold_task_core_vols: int = 80
    # rArBrArB: 2 x (rest A rest B) = 2 x (30+20+30+20) = 200 s -> 80 core vols
    bold_task_dual_core_vols: int = 80
    bold_rest_vols: int = 120  # 5 min, enough for MELODIC/AROMA
    asl_mm: float = 4.0
    pet_mm: float = 4.0
    ct_in_plane_mm: float = 1.0
    ct_slice_mm: float = 2.0


def _cache_key(profile: PhantomProfile, freesurfer_home: str) -> str:
    stamp = ""
    stamp_file = os.path.join(freesurfer_home, "build-stamp.txt")
    if os.path.isfile(stamp_file):
        with open(stamp_file) as handle:
            stamp = handle.read().strip()
    payload = json.dumps(
        {"version": GENERATOR_VERSION, "profile": asdict(profile), "fs": stamp},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _resolve_freesurfer_home(freesurfer_home=None) -> str:
    home = freesurfer_home or os.environ.get("FREESURFER_HOME")
    if not home:
        raise RuntimeError(
            "FREESURFER_HOME is not set; the phantom anatomy is derived from "
            "the fsaverage subject shipped with FreeSurfer."
        )
    return home


def get_phantom_subject(
    profile: PhantomProfile | None = None,
    cache_root: str | None = None,
    freesurfer_home: str | None = None,
    force: bool = False,
) -> str:
    """Return the path of a ready phantom subject folder, building it if needed.

    The returned directory has the layout SWANe expects::

        <subject>/dicom/<data_input_name>/*.dcm

    Parameters
    ----------
    profile : PhantomProfile, optional
        Geometry/timing knobs. Defaults to the coarse "fast" profile.
    cache_root : str, optional
        Overrides ``$SWANE_PHANTOM_DIR`` / the default cache root.
    force : bool
        Rebuild even if a valid cache entry exists.
    """
    profile = profile or PhantomProfile()
    fs_home = _resolve_freesurfer_home(freesurfer_home)
    root = cache_root or os.environ.get("SWANE_PHANTOM_DIR") or DEFAULT_CACHE_ROOT

    key = _cache_key(profile, fs_home)
    subject_dir = os.path.join(root, "phantom_%s" % key)
    manifest_path = os.path.join(subject_dir, "manifest.json")

    if force:
        shutil.rmtree(subject_dir, ignore_errors=True)
    elif os.path.isfile(manifest_path):
        with open(manifest_path) as handle:
            manifest = json.load(handle)
        if manifest.get("complete"):
            return subject_dir

    # Build into a temporary sibling, then move: a crashed run never leaves a
    # half-written dataset that a later run would mistake for a valid cache.
    staging = subject_dir + ".building"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    manifest = build_phantom(staging, profile, fs_home)

    with open(os.path.join(staging, "manifest.json"), "w") as handle:
        json.dump(manifest, handle, indent=2)

    shutil.rmtree(subject_dir, ignore_errors=True)
    os.rename(staging, subject_dir)
    return subject_dir


def build_phantom(
    subject_dir: str, profile: PhantomProfile, freesurfer_home: str, progress=None
) -> dict:
    """Render and write every series of the phantom exam into ``subject_dir``.

    Sequential on purpose: the heavy tail (three fMRI runs writing ~15k tiny
    DICOM files) is I/O-bound, so rendering series in parallel only adds disk
    contention and process overhead without shortening wall time.
    """
    from pydicom.uid import generate_uid

    tissue = build_tissue_model(freesurfer_home)
    dicom_root = os.path.join(subject_dir, DICOM_DIR_NAME)
    os.makedirs(dicom_root, exist_ok=True)

    study_uid = generate_uid()
    entries = build_catalog(profile)
    series_info = []

    for index, entry in enumerate(entries):
        if progress is not None:
            progress(index, len(entries), entry.input_name)
        dest = os.path.join(dicom_root, entry.input_name)
        series_info.append(_write_entry(entry, tissue, dest, study_uid, seed=index))

    return {
        "complete": True,
        "generator_version": GENERATOR_VERSION,
        "profile": asdict(profile),
        "series": series_info,
    }


def _write_entry(entry, tissue, dest, study_uid, seed) -> dict:
    """Render one catalog entry and serialise it as a DICOM series."""
    spec = entry.spec
    common = dict(
        modality=spec.modality,
        series_number=entry.series_number,
        series_description=entry.description,
        study_uid=study_uid,
        tr_s=entry.tr_s,
        te_ms=entry.te_ms,
        flip_angle=entry.flip_angle,
        scanning_sequence=entry.scanning_sequence,
        image_type=entry.image_type,
        rescale_intercept=entry.rescale_intercept,
    )

    if entry.kind == "dwi":
        bvals, bvecs = _dwi_scheme(entry.n_directions, entry.b_value)
        data, affine, bvals, bvecs = render_dwi(
            tissue, spec, bvals, bvecs, seed=seed, pose=entry.pose
        )
        paths = write_volume_series(
            dest, data, affine, bvals=bvals, bvecs=bvecs, **common
        )
        extra = {"bvals": [float(b) for b in bvals], "directions": entry.n_directions}

    elif entry.kind == "bold":
        data, affine, tr_s = render_bold(
            tissue,
            spec,
            n_vols=entry.n_vols,
            tr_s=entry.tr_s,
            design=entry.design,
            seed=seed,
            pose=entry.pose,
        )
        paths = write_volume_series(dest, data, affine, **common)
        extra = {
            "n_vols": entry.n_vols,
            "tr_s": tr_s,
            "design": type(entry.design).__name__,
        }
        if hasattr(entry.design, "paradigm"):
            extra["paradigm"] = entry.design.paradigm
            extra["dummy_start"] = entry.design.dummy_start
            extra["dummy_end"] = entry.design.dummy_end

    elif entry.kind == "venous_pair":
        # Two volumes in a single series: anatomic then velocity-encoded.
        first, affine = render_structural(tissue, spec, seed=seed, pose=entry.pose)
        second_spec = _with_lut(spec, entry.extra["second_lut"])
        second, _ = render_structural(
            tissue, second_spec, seed=seed + 100, pose=entry.pose
        )
        data = np.stack([first, second], axis=-1)
        paths = write_volume_series(dest, data, affine, **common)
        extra = {"n_vols": 2}

    elif entry.kind == "seeg_ct":
        data, affine = render_structural(tissue, spec, seed=seed, pose=entry.pose)
        data = _add_seeg_electrodes(data, affine, tissue)
        paths = write_volume_series(dest, data, affine, **common)
        extra = {"electrodes": True}

    else:
        data, affine = render_structural(tissue, spec, seed=seed, pose=entry.pose)
        paths = write_volume_series(dest, data, affine, **common)
        extra = {}

    info = {
        "input": entry.input_name,
        "description": entry.description,
        "modality": spec.modality,
        "files": len(paths),
        "voxel_mm": spec.voxel_sizes(),
        "misaligned": entry.pose is not None,
        "bias_amp": spec.bias_amp,
    }
    info.update(extra)
    return info


def _with_lut(spec, lut):
    """Copy a SequenceSpec with a different intensity LUT."""
    from dataclasses import replace

    return replace(spec, lut=lut)


def _dwi_scheme(n_directions: int, b_value: float):
    """A minimal, well-conditioned single-shell scheme: 1 b0 + N directions."""
    if n_directions < 6:
        raise ValueError("a tensor fit needs at least 6 directions")
    if n_directions == 6:
        # classic 6-direction icosahedral-style set (mutually non-collinear)
        dirs = np.array(
            [
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (0.707, 0.707, 0.0),
                (0.707, 0.0, 0.707),
                (0.0, 0.707, 0.707),
            ]
        )
    else:
        # spiral (Fibonacci) point set on the hemisphere
        idx = np.arange(n_directions, dtype=float) + 0.5
        phi = np.arccos(1.0 - idx / n_directions)
        theta = np.pi * (1 + 5**0.5) * idx
        dirs = np.stack(
            [np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)],
            axis=1,
        )
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)

    bvals = np.concatenate([[0.0], np.full(len(dirs), float(b_value))])
    bvecs = np.vstack([[0.0, 0.0, 0.0], dirs])
    return bvals, bvecs


def _add_seeg_electrodes(data, affine, tissue, n_electrodes: int = 6):
    """Stamp hyperdense electrode tracks into a CT volume.

    Straight trajectories entering laterally and aiming at deep targets, with
    discrete high-density contacts - what the SEEG workflow looks for.
    """
    from scipy.spatial import cKDTree

    inv = np.linalg.inv(affine)
    shape = data.shape[:3]

    # entry (lateral scalp) -> target (deep, near the midline) in RAS mm
    trajectories = []
    for i in range(n_electrodes):
        side = 1.0 if i % 2 == 0 else -1.0
        y = 30.0 - 20.0 * (i // 2)
        z = 30.0 - 18.0 * (i // 2)
        entry_pt = np.array([side * 75.0, y, z])
        target_pt = np.array([side * 12.0, y * 0.6, z * 0.6])
        trajectories.append((entry_pt, target_pt))

    out = np.asarray(data).copy()
    for entry_pt, target_pt in trajectories:
        length = float(np.linalg.norm(target_pt - entry_pt))
        n_samples = max(int(length / 0.5), 2)
        t = np.linspace(0.0, 1.0, n_samples)[:, None]
        line = entry_pt + (target_pt - entry_pt) * t

        # contacts: 2 mm long every 5 mm along the shaft
        along = np.linspace(0.0, length, n_samples)
        is_contact = (along % 5.0) < 2.0

        vox = line @ inv[:3, :3].T + inv[:3, 3]
        vox = np.rint(vox).astype(int)
        ok = np.all((vox >= 0) & (vox < np.array(shape)), axis=1)
        vox, is_contact = vox[ok], is_contact[ok]
        if not len(vox):
            continue
        # widen to a ~1 voxel radius shaft so it survives partial voluming
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                shifted = vox + np.array([dx, dy, 0])
                inside = np.all((shifted >= 0) & (shifted < np.array(shape)), axis=1)
                sel = shifted[inside]
                vals = np.where(is_contact[inside], 3000, 1600)
                out[sel[:, 0], sel[:, 1], sel[:, 2]] = np.maximum(
                    out[sel[:, 0], sel[:, 1], sel[:, 2]], vals
                )
    return out
