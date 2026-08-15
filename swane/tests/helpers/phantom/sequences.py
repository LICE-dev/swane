"""Stage B - turn the tissue class map into per-modality intensity volumes.

Each sequence is a pure function ``tissue -> (ndarray, affine)`` parameterised by
a :class:`SequenceSpec`: a per-class intensity LUT, a target voxel geometry, a
point-spread blur, a smooth B1 bias field and Rician noise.  The neural-net
tools (SynthStrip/SynthSeg/SynthMorph) re-conform everything to 1 mm 256^3
internally, so their cost is fixed; the target voxel size only speeds up the FSL
path (BET/FLIRT/eddy/dtifit) and recon-all.  Hence the phantom defaults to a
coarse "fast" geometry, tuned per modality.

Nothing here reads fsaverage intensities: only the class codes from
:mod:`swane.tests.helpers.phantom.tissue`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from swane.tests.helpers.phantom.tissue import TissueClass as TC, TissueModel


class Plane(Enum):
    """Acquisition plane -> which output axis carries the thick slices."""

    AXIAL = "axial"  # thick along S (z)
    CORONAL = "coronal"  # thick along A (y)
    SAGITTAL = "sagittal"  # thick along R (x)


# Fraction of a voxel FWHM used as the imaging PSF when none is given.
_DEFAULT_PSF_FRAC = 0.9


@dataclass
class SequenceSpec:
    """Everything needed to render one modality."""

    name: str
    modality: str  # DICOM Modality: MR / CT / PT
    lut: dict  # TissueClass -> mean intensity
    in_plane_mm: float = 2.0
    slice_mm: float = 2.0
    plane: Plane = Plane.AXIAL
    psf_fwhm_mm: float | None = None  # None -> _DEFAULT_PSF_FRAC * voxel
    bias_amp: float = 0.15  # peak-to-peak B1 bias, fraction of signal
    noise_sigma: float = 0.0  # absolute std of the noise
    noise_model: str = "rician"  # "rician" (MR magnitude) | "gaussian" (signed CT)
    background: float = 0.0  # intensity assigned to AIR before noise
    clip_min: float = 0.0
    clip_max: float | None = None
    dtype: str = "int16"
    #: Optional partial coverage, as RAS millimetre limits per axis, e.g.
    #: ``{"A": (-90.0, 32.0)}`` for a coronal slab that only covers the
    #: temporal lobes (plus a margin) instead of the whole head.
    fov_ras: dict | None = None
    #: Optional per-hemisphere intensity override, e.g.
    #: ``{"R": {TissueClass.VENOUS_SINUS: 260}}`` to opacify only the right
    #: dural sinuses (a one-sided contrast CT).  Split by world x (+x = right).
    side_override: dict | None = None

    def voxel_sizes(self) -> list:
        if self.plane is Plane.AXIAL:
            return [self.in_plane_mm, self.in_plane_mm, self.slice_mm]
        if self.plane is Plane.CORONAL:
            return [self.in_plane_mm, self.slice_mm, self.in_plane_mm]
        return [self.slice_mm, self.in_plane_mm, self.in_plane_mm]


# --------------------------------------------------------------------------- #
# Resampling helpers
# --------------------------------------------------------------------------- #
def _lut_volume(tissue: TissueModel, lut: dict, default: float = 0.0) -> np.ndarray:
    """Map class codes to intensities on the native 1 mm grid."""
    out = np.full(tissue.labels.shape, default, dtype=np.float32)
    for cls, val in lut.items():
        out[tissue.labels == int(cls)] = float(val)
    return out


def _apply_side_override(native, tissue, side_override):
    """Override some classes' intensity on one hemisphere, in place.

    ``side_override`` maps ``"L"``/``"R"`` to ``{TissueClass: intensity}``.
    Hemisphere is decided by world x (+x = right) so it works whatever the grid
    orientation.  Used to opacify the venous sinuses on a single side.
    """
    if not side_override:
        return
    ii, jj, kk = np.indices(tissue.labels.shape, dtype=np.float32)
    a = tissue.affine
    world_x = a[0, 0] * ii + a[0, 1] * jj + a[0, 2] * kk + a[0, 3]
    for side, overrides in side_override.items():
        hemi = world_x > 0 if side.upper() == "R" else world_x < 0
        for cls, val in overrides.items():
            native[(tissue.labels == int(cls)) & hemi] = float(val)


def rigid_matrix(
    rotations_deg=(0.0, 0.0, 0.0), translations_mm=(0.0, 0.0, 0.0)
) -> np.ndarray:
    """4x4 rigid transform (RAS mm) from XYZ Euler angles and a translation."""
    rx, ry, rz = np.deg2rad(np.asarray(rotations_deg, dtype=float))
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    out = np.eye(4)
    out[:3, :3] = mz @ my @ mx
    out[:3, 3] = np.asarray(translations_mm, dtype=float)
    return out


def _resample(
    data: np.ndarray,
    affine: np.ndarray,
    voxel_sizes,
    psf_fwhm_mm,
    src_zooms,
    pose: np.ndarray | None = None,
) -> tuple:
    """Anti-aliased resample of ``data`` to ``voxel_sizes`` (RAS output).

    The output grid is a clean, axis-aligned scanner grid derived from the
    *un-posed* anatomy, and that clean affine is what gets written to DICOM.
    ``pose`` then displaces only the *content* on that fixed grid: the anatomy
    ends up sitting slightly off, while the header still describes a normal
    acquisition.  This is the realistic "subject moved between series" case -
    naive header-based alignment does NOT fix it, so a registration that
    silently fails leaves a visible offset in the results.
    """
    import nibabel as nib
    from nibabel.processing import vox2out_vox
    from scipy import ndimage as ndi

    # Pre-blur to the imaging PSF *and* to the target Nyquist to avoid aliasing.
    fwhm = np.asarray([max(psf_fwhm_mm, v) for v in voxel_sizes], dtype=np.float32)
    sigma_vox = (fwhm / np.asarray(src_zooms)) / (2 * np.sqrt(2 * np.log(2)))
    blurred = ndi.gaussian_filter(data, sigma=sigma_vox, mode="nearest")

    # Clean output grid from the *un-posed* image, independent of the pose.
    out_shape, out_affine = vox2out_vox((data.shape, affine), list(voxel_sizes))

    # target voxel index -> source voxel index, optionally through the pose:
    #   world      = out_affine @ idx
    #   anat_world = inv(pose) @ world     (anatomy displaced by the pose)
    #   src_index  = inv(affine) @ anat_world
    transform = np.linalg.inv(affine)
    if pose is not None:
        transform = transform @ np.linalg.inv(pose)
    combined = transform @ out_affine

    out = ndi.affine_transform(
        blurred,
        combined[:3, :3],
        offset=combined[:3, 3],
        output_shape=out_shape,
        order=1,
        mode="constant",
        cval=0.0,
    )
    return np.asarray(out, dtype=np.float32), out_affine


#: RAS axis name -> array axis of a ``resample_to_output`` result (RAS+ canonical)
_RAS_AXIS = {"R": 0, "A": 1, "S": 2}


def _crop_fov(data: np.ndarray, affine: np.ndarray, fov_ras: dict | None):
    """Restrict the field of view to RAS millimetre limits.

    Used for sequences that only cover part of the head - e.g. a coronal T2
    prescribed over the temporal lobes rather than the whole brain.  The affine
    is shifted so world coordinates are preserved.
    """
    if not fov_ras:
        return data, affine

    lo = np.zeros(3, dtype=int)
    hi = np.array(data.shape[:3], dtype=int)
    for axis_name, (mm_min, mm_max) in fov_ras.items():
        axis = _RAS_AXIS[axis_name.upper()]
        step = float(affine[axis, axis])
        origin = float(affine[axis, 3])
        # world = origin + step * index  ->  index = (world - origin) / step
        edges = sorted(((mm_min - origin) / step, (mm_max - origin) / step))
        lo[axis] = max(int(np.floor(edges[0])), 0)
        hi[axis] = min(int(np.ceil(edges[1])) + 1, data.shape[axis])
        if hi[axis] <= lo[axis]:
            raise ValueError(
                "fov_ras %s=%s does not intersect the rendered volume"
                % (axis_name, (mm_min, mm_max))
            )

    sl = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
    cropped = data[sl]
    new_affine = affine.copy()
    new_affine[:3, 3] = affine[:3, :3] @ lo + affine[:3, 3]
    return cropped, new_affine


def _bias_field(shape: tuple, amp: float, rng: np.random.Generator) -> np.ndarray:
    """Smooth multiplicative B1 inhomogeneity, mean 1, span ``amp``.

    Built from a few low-order spatial harmonics rather than filtered noise, so
    it is genuinely low-frequency (what N4/FAST-style bias correction is meant
    to recover) and cheap to evaluate on large grids.  Sequences that exist to
    exercise bias correction (3D T1w, 3D FLAIR) pass a large ``amp``.
    """
    if amp <= 0:
        return np.ones(shape, dtype=np.float32)

    axes = [np.linspace(-1.0, 1.0, n, dtype=np.float32) for n in shape]
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")

    field = np.zeros(shape, dtype=np.float32)
    # random but smooth: a handful of low-order terms with random weights
    for gradient in (gx, gy, gz):
        field += rng.uniform(-1.0, 1.0) * gradient
        field += rng.uniform(-0.6, 0.6) * gradient**2
    field += rng.uniform(-0.5, 0.5) * gx * gy
    field += rng.uniform(-0.5, 0.5) * gx * gz
    field += rng.uniform(-0.5, 0.5) * gy * gz

    span = float(field.max() - field.min()) or 1.0
    field = (field - field.min()) / span  # -> [0, 1]
    return (1.0 - amp / 2.0 + amp * field).astype(np.float32)


def _rician(clean: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    if sigma <= 0:
        return clean
    real = clean + rng.normal(0, sigma, clean.shape)
    imag = rng.normal(0, sigma, clean.shape)
    return np.sqrt(real**2 + imag**2).astype(np.float32)


def _add_noise(clean, sigma, model, rng):
    """Apply the sequence noise model.

    Rician is the correct magnitude-MR model, but it rectifies negatives - fatal
    for CT, whose Hounsfield scale is signed (air is about -1000 HU) and would
    otherwise be flipped positive.  Signed modalities use Gaussian noise.
    """
    if sigma <= 0:
        return clean
    if model == "gaussian":
        return (clean + rng.normal(0, sigma, clean.shape)).astype(np.float32)
    return _rician(clean, sigma, rng)


def _finish(data, spec, rng) -> np.ndarray:
    data = data * _bias_field(data.shape, spec.bias_amp, rng)
    data = _add_noise(data, spec.noise_sigma, spec.noise_model, rng)
    cmax = spec.clip_max
    data = np.clip(data, spec.clip_min, cmax if cmax is not None else None)
    if spec.dtype.startswith("int") or spec.dtype.startswith("uint"):
        data = np.rint(data)
    return data.astype(spec.dtype)


# --------------------------------------------------------------------------- #
# Public renderers
# --------------------------------------------------------------------------- #
def render_structural(
    tissue: TissueModel,
    spec: SequenceSpec,
    seed: int = 0,
    pose: np.ndarray | None = None,
) -> tuple:
    """Render a single 3D volume (T1w/FLAIR/T2/CT/PET/ASL/PC-MRA anatomic)."""
    rng = np.random.default_rng(seed)
    psf = spec.psf_fwhm_mm or _DEFAULT_PSF_FRAC * min(spec.voxel_sizes())
    native = _lut_volume(tissue, spec.lut, default=spec.background)
    _apply_side_override(native, tissue, spec.side_override)
    data, affine = _resample(
        native, tissue.affine, spec.voxel_sizes(), psf, tissue.zooms, pose
    )
    data, affine = _crop_fov(data, affine, spec.fov_ras)
    return _finish(data, spec, rng), affine


def render_dwi(
    tissue: TissueModel,
    spec: SequenceSpec,
    bvals,
    bvecs,
    seed: int = 0,
    pose: np.ndarray | None = None,
) -> tuple:
    """Render a 4D single-shell DWI whose CST voxels are anisotropic.

    Signal model per voxel: ``S = S0 * exp(-b * gT D g)`` with an isotropic
    tensor everywhere except along the cortico-spinal corridor, whose principal
    axis follows the local corridor direction so ``dtifit`` recovers high FA
    there and low FA elsewhere.

    Returns ``(data4d, affine, bvals, bvecs)``.
    """
    rng = np.random.default_rng(seed)
    psf = spec.psf_fwhm_mm or _DEFAULT_PSF_FRAC * min(spec.voxel_sizes())

    s0_native = _lut_volume(tissue, spec.lut, default=spec.background)
    s0, affine = _resample(
        s0_native, tissue.affine, spec.voxel_sizes(), psf, tissue.zooms, pose
    )

    # resample CST membership to the DWI grid; the corridor runs roughly
    # infero-superior, so its principal diffusion axis is ~ RAS +z (superior).
    # A constant axis is far cheaper than a full direction field and still
    # yields high FA along the tract and low FA elsewhere.
    cst_native = tissue.cst.astype(np.float32)
    cst, _ = _resample(
        cst_native, tissue.affine, spec.voxel_sizes(), psf, tissue.zooms, pose
    )
    cst_mask = cst > 0.3

    # Per-voxel principal diffusion axis, following the bundle's curvature.  A
    # single global axis makes the tract effectively straight, and tractography
    # then leaves it where the real tract bends (internal capsule, peduncle) -
    # which is why the reconstructed bundle came out threadlike.
    princ = _resample_direction_field(tissue, spec, psf, pose, cst_mask.shape)
    if pose is not None:
        # the pose rotates the anatomy, so the fibre directions rotate with it
        princ = np.einsum("ij,jxyz->ixyz", np.linalg.inv(pose)[:3, :3], princ)
        norm = np.sqrt((princ**2).sum(axis=0)) + 1e-6
        princ = princ / norm

    d_par, d_perp, d_iso = 1.7e-3, 0.3e-3, 0.9e-3  # mm^2/s
    bvals = np.asarray(bvals, dtype=np.float32)
    bvecs = np.asarray(bvecs, dtype=np.float32)

    # B1 shading is a property of the scanner/run, so it is computed once and
    # shared by every volume (also keeps peak memory flat for large 4D series).
    bias = _bias_field(s0.shape, spec.bias_amp, rng)
    cmax = spec.clip_max

    data = np.zeros(s0.shape + (len(bvals),), dtype=spec.dtype)
    for i, (b, g) in enumerate(zip(bvals, bvecs)):
        if b <= 0:
            atten = np.ones_like(s0)
        else:
            # isotropic background
            atten = np.full(s0.shape, np.exp(-b * d_iso), dtype=np.float32)
            # anisotropic in the CST: gT D g, with the principal axis varying
            # voxel by voxel along the tract
            gdot = princ[0] * g[0] + princ[1] * g[1] + princ[2] * g[2]
            g_perp2 = np.clip(1.0 - gdot**2, 0.0, 1.0)
            gDg = d_par * gdot**2 + d_perp * g_perp2
            atten = np.where(cst_mask, np.exp(-b * gDg), atten)
        vol = _rician(s0 * atten * bias, spec.noise_sigma, rng)
        np.clip(vol, spec.clip_min, cmax, out=vol)
        data[..., i] = np.rint(vol)

    return data, affine, bvals, bvecs


def _resample_direction_field(tissue, spec, psf, pose, target_shape):
    """Resample the CST fibre directions onto the output grid, re-normalised.

    Falls back to a superior-pointing axis where the tract has no direction
    (older tissue models, or voxels the interpolation left at zero).
    """
    field = getattr(tissue, "cst_dir", None)
    if field is None:
        out = np.zeros((3,) + target_shape, dtype=np.float32)
        out[2] = 1.0
        return out

    comps = []
    for axis in range(3):
        resampled, _ = _resample(
            np.ascontiguousarray(field[..., axis]),
            tissue.affine,
            spec.voxel_sizes(),
            psf,
            tissue.zooms,
            pose,
        )
        comps.append(resampled)
    princ = np.stack(comps, axis=0)

    norm = np.sqrt((princ**2).sum(axis=0))
    empty = norm < 1e-3
    princ[2] = np.where(empty, 1.0, princ[2])
    princ[0] = np.where(empty, 0.0, princ[0])
    princ[1] = np.where(empty, 0.0, princ[1])
    norm = np.sqrt((princ**2).sum(axis=0)) + 1e-6
    return (princ / norm).astype(np.float32)


def render_bold(
    tissue: TissueModel,
    spec: SequenceSpec,
    *,
    n_vols: int,
    tr_s: float,
    design,
    activation_frac: float = 0.03,
    seed: int = 0,
    pose: np.ndarray | None = None,
) -> tuple:
    """Render a 4D BOLD EPI series driven by a ``design`` descriptor.

    ``design`` is one of :class:`TaskDesign` or :class:`RestingDesign`; it turns
    into a list of *signal components* ``(spatial_map, time_course)`` that are
    each added as ``base * frac * map * tc[v]``.  Components are applied one
    volume at a time, so no 4D temporary is ever allocated (these are the
    largest series of the exam).

    Returns ``(data4d, affine, tr_s)``.
    """
    rng = np.random.default_rng(seed)
    psf = spec.psf_fwhm_mm or _DEFAULT_PSF_FRAC * min(spec.voxel_sizes())

    base_native = _lut_volume(tissue, spec.lut, default=spec.background)
    base, affine = _resample(
        base_native, tissue.affine, spec.voxel_sizes(), psf, tissue.zooms, pose
    )

    components = _bold_components(
        design,
        tissue,
        spec,
        base,
        affine,
        psf,
        pose,
        n_vols,
        tr_s,
        activation_frac,
        rng,
    )

    # T1-saturation gain on the dummy volumes at the ends of a task run, so the
    # del_start_vols/del_end_vols steps have identifiable volumes to trim.
    dummy_start = getattr(design, "dummy_start", 0)
    dummy_end = getattr(design, "dummy_end", 0)
    gain = _dummy_gain(n_vols, dummy_start, dummy_end)

    bias = _bias_field(base.shape, spec.bias_amp, rng)
    cmax = spec.clip_max

    data = np.zeros(base.shape + (n_vols,), dtype=spec.dtype)
    for v in range(n_vols):
        vol = base * (bias * gain[v])
        for smap, tcourse in components:
            vol = vol + base * (tcourse[v] * smap)
        vol = _rician(vol, spec.noise_sigma, rng)
        np.clip(vol, spec.clip_min, cmax, out=vol)
        data[..., v] = np.rint(vol)

    return data, affine, tr_s


# --------------------------------------------------------------------------- #
# BOLD design descriptors
# --------------------------------------------------------------------------- #
@dataclass
class TaskDesign:
    """A block-design motor task.

    ``paradigm`` mirrors SWANe's ``BlockDesign``:

    * ``"RARA"``   - rest / A / rest / A ...   (single condition A)
    * ``"RARBRARB"`` - rest / A / rest / B ... (two conditions A and B)

    The conditions are motor tasks and activation is **contralateral**: A is a
    right-hand task, so it lights up the *left* precentral cortex; B is a
    left-hand task lighting the *right* precentral cortex.

    ``task_s`` and ``rest_s`` are independent so the two block lengths can
    differ.  ``dummy_start`` / ``dummy_end`` add non-task volumes at the ends
    that carry a T1-saturation brightness bump - the "dummy scans" a real
    acquisition discards, here so ``del_start_vols`` / ``del_end_vols`` have
    something identifiable to remove.  Block timing is measured from the first
    non-dummy volume.
    """

    paradigm: str = "RARA"
    task_s: float = 30.0
    rest_s: float = 30.0
    dummy_start: int = 0
    dummy_end: int = 0


@dataclass
class RestingDesign:
    """Resting state: named networks + a nuisance component (AROMA target)."""

    n_networks: int = 2
    n_noise: int = 1


def _bold_components(
    design, tissue, spec, base, affine, psf, pose, n_vols, tr_s, frac, rng
):
    """Build ``(spatial_map, time_course)`` pairs for a BOLD ``design``."""
    if isinstance(design, TaskDesign):
        return _task_components(
            design, tissue, spec, base, affine, psf, pose, n_vols, tr_s, frac
        )
    if isinstance(design, RestingDesign):
        return _resting_components(
            design, tissue, spec, base, affine, psf, pose, n_vols, tr_s, frac, rng
        )
    raise TypeError("unknown BOLD design %r" % type(design))


def _precentral_side_mask(tissue, spec, affine, psf, pose, side):
    """Resampled precentral mask for one hemisphere (``'L'`` or ``'R'``)."""
    native = (tissue.labels == int(TC.PRECENTRAL_GM)).astype(np.float32)
    # split by world x: RAS +x is the right hemisphere
    idx = np.argwhere(native > 0)
    if len(idx):
        world_x = idx @ tissue.affine[:3, :3].T[:, 0] + tissue.affine[0, 3]
        keep = world_x < 0 if side == "L" else world_x > 0
        drop = idx[~keep]
        native[drop[:, 0], drop[:, 1], drop[:, 2]] = 0.0
    resampled, _ = _resample(
        native, tissue.affine, spec.voxel_sizes(), psf, tissue.zooms, pose
    )
    return (resampled > 0.3).astype(np.float32)


def _dummy_gain(n_vols, dummy_start, dummy_end):
    """Per-volume brightness gain: a decaying T1-saturation bump on the dummies.

    The leading dummy volumes start ~35% brighter and relax toward 1; the
    trailing dummies carry a smaller constant bump.  Both are clear enough to
    verify that ``del_start_vols`` / ``del_end_vols`` removed them.
    """
    gain = np.ones(n_vols, dtype=np.float32)
    for v in range(min(dummy_start, n_vols)):
        gain[v] = 1.0 + 0.35 * np.exp(-v / 2.0)
    for j in range(min(dummy_end, n_vols)):
        gain[n_vols - 1 - j] = 1.0 + 0.15
    return gain


def _task_components(design, tissue, spec, base, affine, psf, pose, n_vols, tr_s, frac):
    period = design.rest_s + design.task_s
    dummy_start = design.dummy_start
    dummy_end = design.dummy_end
    core_end_vol = n_vols - dummy_end

    left = _precentral_side_mask(tissue, spec, affine, psf, pose, "L")
    right = _precentral_side_mask(tissue, spec, affine, psf, pose, "R")

    def _gated(active):
        """Wrap a time predicate so it is off during the dummy volumes.

        The predicate receives *task time*, measured from the first non-dummy
        volume, so the block timing ignores the leading dummies.
        """

        def predicate_by_volume(v):
            if v < dummy_start or v >= core_end_vol:
                return False
            return active((v - dummy_start) * tr_s)

        return predicate_by_volume

    def _boxcar(predicate_by_volume):
        boxcar = np.array(
            [1.0 if predicate_by_volume(v) else 0.0 for v in range(n_vols)],
            dtype=np.float32,
        )
        ts = _convolve_hrf(boxcar, tr_s)
        return ts / (np.abs(ts).max() or 1.0)

    def in_a(x):  # condition A active: task block after each rest block
        return (x % period) >= design.rest_s

    components = []
    if design.paradigm.upper() == "RARA":
        # single condition A (right hand) -> left precentral
        components.append((frac * left, _boxcar(_gated(in_a))))
    elif design.paradigm.upper() == "RARBRARB":
        # A blocks and B blocks alternate: r A r B r A r B ...
        double = 2 * period

        def in_a2(x):
            return design.rest_s <= (x % double) < period

        def in_b2(x):
            return (x % double) >= (period + design.rest_s)

        components.append((frac * left, _boxcar(_gated(in_a2))))
        components.append((frac * right, _boxcar(_gated(in_b2))))
    else:
        raise ValueError("unknown paradigm %r" % design.paradigm)
    return components


def _resting_components(
    design, tissue, spec, base, affine, psf, pose, n_vols, tr_s, frac, rng
):
    """Two anatomical networks + broadband nuisance, each rank-1 in time."""
    from scipy import ndimage as ndi

    brain = base > (0.05 * float(base.max() or 1.0))
    components = []

    def low_freq_tc():
        freq = rng.uniform(0.01, 0.08)  # classic RSN band
        phase = rng.uniform(0, 2 * np.pi)
        return np.sin(2 * np.pi * freq * np.arange(n_vols) * tr_s + phase).astype(
            np.float32
        )

    # Network 1: sensorimotor (bilateral precentral), smoothed for realism
    motor = _precentral_side_mask(
        tissue, spec, affine, psf, pose, "L"
    ) + _precentral_side_mask(tissue, spec, affine, psf, pose, "R")
    motor = ndi.gaussian_filter(motor, 1.5)
    if motor.max() > 0:
        components.append((frac * motor / motor.max(), low_freq_tc()))

    # Network 2: posterior-medial cortex (precuneus/occipital-like), from the
    # cortical GM in a posterior, near-midline RAS box.
    if design.n_networks >= 2:
        post = _ras_box_mask(
            tissue,
            spec,
            affine,
            psf,
            pose,
            r=(-30, 30),
            a=(-95, -45),
            s=(-5, 45),
            classes=(TC.CORTICAL_GM, TC.PRECENTRAL_GM),
        )
        post = ndi.gaussian_filter(post, 1.5)
        if post.max() > 0:
            components.append((frac * post / post.max(), low_freq_tc()))

    # Nuisance: broad smooth map over the whole brain with a broadband time
    # course (spans beyond the RSN band) - what ICA-AROMA should flag as noise.
    for _ in range(design.n_noise):
        smap = ndi.gaussian_filter(
            rng.standard_normal(base.shape).astype(np.float32), 4
        )
        smap *= brain
        smap /= np.abs(smap).max() or 1.0
        noise_tc = rng.standard_normal(n_vols).astype(np.float32)
        components.append((0.6 * frac * smap, noise_tc))

    return components


def _ras_box_mask(tissue, spec, affine, psf, pose, r, a, s, classes):
    """Resampled mask of ``classes`` restricted to an RAS millimetre box."""
    sel = np.isin(tissue.labels, [int(c) for c in classes])
    idx = np.argwhere(sel)
    if len(idx):
        world = idx @ tissue.affine[:3, :3].T + tissue.affine[:3, 3]
        keep = (
            (world[:, 0] >= r[0])
            & (world[:, 0] <= r[1])
            & (world[:, 1] >= a[0])
            & (world[:, 1] <= a[1])
            & (world[:, 2] >= s[0])
            & (world[:, 2] <= s[1])
        )
        native = np.zeros(tissue.labels.shape, dtype=np.float32)
        kept = idx[keep]
        native[kept[:, 0], kept[:, 1], kept[:, 2]] = 1.0
    else:
        native = np.zeros(tissue.labels.shape, dtype=np.float32)
    resampled, _ = _resample(
        native, tissue.affine, spec.voxel_sizes(), psf, tissue.zooms, pose
    )
    return (resampled > 0.3).astype(np.float32)


def _convolve_hrf(x: np.ndarray, tr_s: float) -> np.ndarray:
    """Convolve a boxcar with a double-gamma HRF sampled at ``tr_s``."""
    from scipy.stats import gamma

    t = np.arange(0, 32, tr_s)
    hrf = gamma.pdf(t, 6) - 0.35 * gamma.pdf(t, 16)
    hrf /= hrf.sum() or 1.0
    return np.convolve(x, hrf)[: len(x)]
