"""Stage A - build a tissue *class map* from the FreeSurfer ``fsaverage`` subject.

The output is a single ``int16`` volume whose voxels hold a
:class:`TissueClass` code, in real anatomical scale (fsaverage is a 1 mm
isotropic 256^3 conformed volume in MNI305 space).  Every later stage only ever
looks at these class codes, never at fsaverage intensities, so the phantom is
fully under our control and reproducible.

Only ``fsaverage`` is read (it ships with FreeSurfer), so nothing subject- or
licence-restricted is involved.

Extracerebral tissue (CSF gap, skull, scalp, background air) is *not* copied
from ``fsaverage`` (whose averaged T1 has a blurred, unusable skull); it is
synthesised as clean concentric shells grown outward from the brain mask with a
Euclidean distance transform.  Sharp shell edges are exactly what BET /
SynthStrip need to behave like they do on real heads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import IntEnum

import numpy as np


class TissueClass(IntEnum):
    """Voxel classes of the phantom tissue map."""

    AIR = 0  # background / paranasal air
    CORTICAL_GM = 1  # cortical grey matter
    DEEP_GM = 2  # thalamus, basal ganglia
    WM = 3  # cerebral white matter
    CSF_VENTRICLE = 4  # ventricular CSF
    CSF_EXTRA = 5  # extra-axial / subarachnoid CSF
    CEREBELLUM_GM = 6
    CEREBELLUM_WM = 7
    BRAINSTEM = 8
    # --- synthesised extracerebral shells ---
    SKULL = 9  # cortical bone (very dark on MR, very bright on CT)
    DIPLOE = 10  # marrow between bone tables (fatty)
    SCALP = 11  # skin + subcutaneous fat
    # --- feature overlays (do not change the base tissue, add semantics) ---
    PRECENTRAL_GM = 12  # motor cortex: fMRI activation source + CST origin
    CST = 13  # cortico-spinal tract corridor (anisotropic in DWI)
    VENOUS_SINUS = 14  # dural venous sinuses (venous MR/CT)


# fsaverage / FreeSurfer aseg label ids we consume.
_FS = {
    "wm": (2, 41),
    "cortex": (3, 42),
    "thalamus": (10, 49),
    "caudate": (11, 50),
    "putamen": (12, 51),
    "pallidum": (13, 52),
    "hippocampus": (17, 53),
    "amygdala": (18, 54),
    "accumbens": (26, 58),
    "ventral_dc": (28, 60),
    "ventricle": (4, 43, 14, 15, 5, 44, 72),
    "csf": (24,),
    "cerebellum_wm": (7, 46),
    "cerebellum_gm": (8, 47),
    "brainstem": (16,),
}

# aparc precentral gyrus (Desikan-Killiany): ctx-lh/rh-precentral.
_PRECENTRAL = (1024, 2024)


@dataclass
class TissueModel:
    """Result of stage A."""

    labels: np.ndarray  # int16, TissueClass codes
    affine: np.ndarray  # 4x4, voxel -> RAS (MNI305), from fsaverage
    zooms: tuple  # mm, (1, 1, 1) for fsaverage
    #: reference feature masks in the same grid, handy for later stages/tests
    precentral: np.ndarray  # bool, motor cortex
    cst: np.ndarray  # bool, cortico-spinal corridor
    #: (X, Y, Z, 3) unit fibre direction in RAS inside the CST, zero elsewhere;
    #: follows the bundle's curvature so tractography can track through it
    cst_dir: np.ndarray = None


def _fsaverage_dir(freesurfer_home: str | None = None) -> str:
    home = freesurfer_home or os.environ.get("FREESURFER_HOME")
    if not home:
        raise RuntimeError(
            "FREESURFER_HOME is not set; cannot locate the fsaverage subject "
            "needed to build the phantom anatomy."
        )
    path = os.path.join(home, "subjects", "fsaverage", "mri")
    if not os.path.isdir(path):
        raise RuntimeError("fsaverage not found at %s" % path)
    return path


def _load(fs_mri: str, name: str) -> np.ndarray:
    import nibabel as nib

    return np.asarray(nib.load(os.path.join(fs_mri, name)).dataobj)


def _in(vol: np.ndarray, labels) -> np.ndarray:
    return np.isin(vol, np.asarray(labels, dtype=vol.dtype))


def build_tissue_model(
    freesurfer_home: str | None = None,
    crop_margin_mm: float = 12.0,
    deform: bool = True,
) -> TissueModel:
    """Construct the phantom tissue class map from ``fsaverage``.

    Parameters
    ----------
    freesurfer_home : str, optional
        Overrides ``$FREESURFER_HOME``.
    crop_margin_mm : float
        The 256^3 fsaverage grid is cropped to the head bounding box plus this
        air margin, which cuts memory and render time for the coarse "fast"
        profile without changing world coordinates.  Set to a negative value to
        keep the full 256^3 grid.
    deform : bool
        Apply the fixed smooth non-linear deformation (see
        :mod:`swane.tests.helpers.phantom.deformation`) to the anatomy before
        cropping. On by default and deterministic, so the generator and the
        ground-truth checks build the *same* deformed subject. Turn off only to
        inspect the undeformed anatomy.

    Returns
    -------
    TissueModel
    """
    import nibabel as nib
    from scipy import ndimage as ndi

    fs_mri = _fsaverage_dir(freesurfer_home)
    aseg = _load(fs_mri, "aseg.mgz").astype(np.int32)
    aparc = _load(fs_mri, "aparc+aseg.mgz").astype(np.int32)
    ref_img = nib.load(os.path.join(fs_mri, "aseg.mgz"))
    affine = ref_img.affine.copy()
    zooms = tuple(float(z) for z in ref_img.header.get_zooms()[:3])

    labels = np.full(aseg.shape, TissueClass.AIR, dtype=np.int16)

    # --- intracranial tissue from aseg (order matters: broad first) ---
    labels[_in(aseg, _FS["wm"])] = TissueClass.WM
    labels[_in(aseg, _FS["cortex"])] = TissueClass.CORTICAL_GM
    for key in (
        "thalamus",
        "caudate",
        "putamen",
        "pallidum",
        "accumbens",
        "ventral_dc",
        "hippocampus",
        "amygdala",
    ):
        labels[_in(aseg, _FS[key])] = TissueClass.DEEP_GM
    labels[_in(aseg, _FS["cerebellum_wm"])] = TissueClass.CEREBELLUM_WM
    labels[_in(aseg, _FS["cerebellum_gm"])] = TissueClass.CEREBELLUM_GM
    labels[_in(aseg, _FS["brainstem"])] = TissueClass.BRAINSTEM
    labels[_in(aseg, _FS["ventricle"])] = TissueClass.CSF_VENTRICLE
    labels[_in(aseg, _FS["csf"])] = TissueClass.CSF_EXTRA

    brain = labels != TissueClass.AIR

    # --- synthesise extracerebral shells by distance from the brain mask ---
    # distance (mm) from the nearest brain voxel, isotropic 1 mm grid
    dist = ndi.distance_transform_edt(~brain, sampling=zooms)
    # subarachnoid CSF just outside the brain, then bone, then scalp/fat
    csf_gap = (dist > 0) & (dist <= 2.5)
    bone = (dist > 2.5) & (dist <= 7.0)
    diploe = (dist > 3.8) & (dist <= 5.7)  # marrow core inside the bone table
    scalp = (dist > 7.0) & (dist <= 12.0)

    labels[csf_gap] = TissueClass.CSF_EXTRA
    labels[bone] = TissueClass.SKULL
    labels[diploe] = TissueClass.DIPLOE
    labels[scalp] = TissueClass.SCALP
    # everything farther out stays AIR

    # --- feature overlays ------------------------------------------------
    precentral = _in(aparc, _PRECENTRAL) & _in(aseg, _FS["cortex"])
    cst, cst_dir = _build_cst(brain, precentral, aseg, zooms, affine)

    out = labels.copy()
    out[precentral] = TissueClass.PRECENTRAL_GM
    # CST runs through WM; only stamp where it overlaps white matter/brainstem
    cst_stampable = cst & np.isin(
        labels, [TissueClass.WM, TissueClass.BRAINSTEM, TissueClass.CEREBELLUM_WM]
    )
    out[cst_stampable] = TissueClass.CST
    cst_dir[~cst_stampable] = 0.0

    venous = _build_venous_sinuses(brain, aseg, zooms, affine)
    out[venous & (out == TissueClass.CSF_EXTRA)] = TissueClass.VENOUS_SINUS

    # Warp the whole subject by the fixed smooth field *before* cropping, so the
    # head bounding box is measured on the deformed anatomy and nothing is
    # clipped. Labels, feature masks and the fibre directions move together.
    if deform:
        from swane.tests.helpers.phantom.deformation import deform_anatomy

        out, warped_masks, cst_dir = deform_anatomy(
            out,
            {"precentral": precentral, "cst": cst_stampable},
            cst_dir,
            affine,
            zooms,
        )
        precentral = warped_masks["precentral"]
        cst_stampable = warped_masks["cst"]

    precentral_out = precentral
    cst_out = cst_stampable
    if crop_margin_mm >= 0:
        out, affine, (sl, precentral_out, cst_out) = _crop_to_head(
            out, affine, zooms, crop_margin_mm, [precentral, cst_stampable]
        )
        cst_dir = cst_dir[sl]

    return TissueModel(
        labels=out,
        affine=affine,
        zooms=zooms,
        precentral=precentral_out,
        cst=cst_out,
        cst_dir=cst_dir,
    )


def _crop_to_head(labels, affine, zooms, margin_mm, extra_masks):
    """Crop the label grid to its non-air bounding box + an isotropic margin.

    Returns ``(labels_cropped, affine_cropped, (slices, *extra_cropped))`` with
    ``affine`` updated so world coordinates are preserved.
    """
    fg = np.argwhere(labels != TissueClass.AIR)
    if fg.size == 0:
        return labels, affine, (tuple(slice(None) for _ in labels.shape), *extra_masks)
    lo = fg.min(axis=0)
    hi = fg.max(axis=0) + 1
    margin = np.ceil(margin_mm / np.asarray(zooms)).astype(int)
    lo = np.maximum(lo - margin, 0)
    hi = np.minimum(hi + margin, labels.shape)
    sl = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))

    new_affine = affine.copy()
    new_affine[:3, 3] = affine[:3, :3] @ lo + affine[:3, 3]
    cropped_extra = [m[sl] for m in extra_masks]
    return labels[sl], new_affine, (sl, *cropped_extra)


# Cortico-spinal tract course, as RAS(mm) waypoints for the LEFT side; the
# right side is the x-mirror.  Coordinates follow the classic descending route
# and were checked against the fsaverage aseg (see comment per waypoint).
# ``radius_mm`` is deliberately generous: the phantom bundle must *contain* the
# real tract so ROI-based tractography still intersects it.  Width is the safety
# margin - the waypoints themselves stay centred on the true course, since a
# wide-but-centred bundle is what keeps automatic ROIs on target.
_CST_WAYPOINTS_L = [
    # (R, A, S) mm,                radius_mm,  lands in (fsaverage aseg)
    ((-34.0, -12.0, 48.0), 11.0),  # M1 / precentral white matter -> WM
    ((-26.0, -14.0, 28.0), 10.0),  # corona radiata               -> WM
    ((-20.0, -14.0, 4.0), 8.0),  # posterior limb internal caps. -> WM
    ((-12.0, -20.0, -14.0), 7.0),  # cerebral peduncle             -> ventralDC
    ((-8.0, -22.0, -30.0), 6.5),  # basis pontis                  -> brainstem
    ((-5.0, -30.0, -48.0), 5.5),  # medullary pyramid             -> brainstem
]


def _build_cst(brain, precentral, aseg, zooms, affine):
    """Cortico-spinal corridor following the real descending anatomy.

    The bundle is a smooth tube through anatomical waypoints (M1 -> corona
    radiata -> posterior limb of the internal capsule -> cerebral peduncle ->
    basis pontis -> medullary pyramid), built in RAS millimetres so it does not
    depend on the array axis order (fsaverage is LIA, not RAS).
    """
    from scipy import ndimage as ndi

    corridor = np.zeros(brain.shape, dtype=bool)
    # Unit fibre direction (RAS) per voxel.  A single global axis would make the
    # bundle straight, and tractography then leaves it wherever the real tract
    # bends (internal capsule, cerebral peduncle); following the local tangent
    # keeps the fibres inside the curving bundle.
    direction = np.zeros(brain.shape + (3,), dtype=np.float32)
    for mirror in (1.0, -1.0):
        pts = np.array(
            [[w[0][0] * mirror, w[0][1], w[0][2]] for w in _CST_WAYPOINTS_L],
            dtype=np.float64,
        )
        radii = np.array([w[1] for w in _CST_WAYPOINTS_L], dtype=np.float64)
        curve, curve_r = _resample_polyline(pts, radii, step_mm=0.5)
        tangents = _curve_tangents(curve)
        corridor |= _tube_ras(
            brain.shape, affine, curve, curve_r, tangents=tangents, dir_out=direction
        )

    corridor &= brain
    corridor = ndi.binary_closing(corridor, iterations=1)
    direction[~corridor] = 0.0
    return corridor, direction


def _curve_tangents(curve):
    """Unit tangent at every point of a densely sampled polyline."""
    tangents = np.gradient(curve, axis=0)
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (tangents / norms).astype(np.float32)


def _resample_polyline(points, radii, step_mm=0.5):
    """Densely sample a Catmull-Rom spline through ``points``.

    Returns ``(curve_points, curve_radii)`` in the same units as ``points``.
    """
    # pad the ends so the spline spans every original waypoint
    p = np.vstack([points[0], points, points[-1]])
    r = np.concatenate([radii[:1], radii, radii[-1:]])

    out_pts, out_rad = [], []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        seg_len = float(np.linalg.norm(p2 - p1))
        n = max(int(np.ceil(seg_len / step_mm)), 2)
        t = np.linspace(0.0, 1.0, n, endpoint=False)[:, None]
        # Catmull-Rom basis
        pos = 0.5 * (
            (2 * p1)
            + (-p0 + p2) * t
            + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
            + (-p0 + 3 * p1 - 3 * p2 + p3) * t**3
        )
        out_pts.append(pos)
        out_rad.append(r[i] + (r[i + 1] - r[i]) * t[:, 0])
    out_pts.append(p[-2][None, :])
    out_rad.append(r[-2:-1])
    return np.vstack(out_pts), np.concatenate(out_rad)


def _tube_ras(shape, affine, curve_ras, curve_radii, tangents=None, dir_out=None):
    """Voxels whose RAS centre lies within the (variable) tube radius.

    Only the curve's bounding box (plus the largest radius) is searched, which
    keeps the KD-tree query small.

    When ``tangents`` and ``dir_out`` are given, every voxel inside the tube also
    receives the unit tangent of its nearest curve point, so the bundle carries a
    direction that follows its curvature instead of a single global axis.
    """
    from scipy.spatial import cKDTree

    inv = np.linalg.inv(affine)
    max_r = float(curve_radii.max())

    # bounding box of the tube in voxel space
    corners_ras = np.array(
        [
            curve_ras.min(axis=0) - max_r,
            curve_ras.max(axis=0) + max_r,
        ]
    )
    box = []
    for corner in np.array(np.meshgrid(*corners_ras.T)).reshape(3, -1).T:
        box.append(inv[:3, :3] @ corner + inv[:3, 3])
    box = np.array(box)
    lo = np.maximum(np.floor(box.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.ceil(box.max(axis=0)).astype(int) + 1, shape)

    out = np.zeros(shape, dtype=bool)
    if np.any(lo >= hi):
        return out

    grids = np.meshgrid(*[np.arange(a, b) for a, b in zip(lo, hi)], indexing="ij")
    idx = np.stack([g.ravel() for g in grids], axis=1)
    ras = idx @ affine[:3, :3].T + affine[:3, 3]

    tree = cKDTree(curve_ras)
    dist, nearest = tree.query(ras, k=1)
    inside = dist <= curve_radii[nearest]

    sel = idx[inside]
    out[sel[:, 0], sel[:, 1], sel[:, 2]] = True

    if tangents is not None and dir_out is not None and len(sel):
        vecs = tangents[nearest[inside]]
        dir_out[sel[:, 0], sel[:, 1], sel[:, 2], :] = vecs
    return out


def _build_venous_sinuses(brain, aseg, zooms, affine):
    """Dural venous sinuses: superior sagittal + transverse, in RAS mm.

    Enough for the venous MR/CT workflows to have a hyperintense/hyperdense
    vessel to segment; not an anatomically exact sinus tree.
    """
    from scipy import ndimage as ndi

    dist = ndi.distance_transform_edt(~brain, sampling=zooms)
    rim = (dist > 0) & (dist <= 3.5)  # dural rim hugging the brain surface

    idx = np.argwhere(rim)
    if idx.size == 0:
        return np.zeros(brain.shape, dtype=bool)
    ras = idx @ affine[:3, :3].T + affine[:3, 3]
    x, y, z = ras[:, 0], ras[:, 1], ras[:, 2]

    # superior sagittal sinus: midline slab, from the vertex down the occiput
    sss = (np.abs(x) <= 4.0) & (z >= -10.0)
    # transverse sinuses: posterior, roughly horizontal, running laterally
    transverse = (y <= -35.0) & (z >= -30.0) & (z <= 5.0) & (np.abs(x) <= 55.0)

    keep = idx[sss | transverse]
    out = np.zeros(brain.shape, dtype=bool)
    out[keep[:, 0], keep[:, 1], keep[:, 2]] = True
    return out
