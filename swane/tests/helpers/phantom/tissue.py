"""Stage A - build a tissue *class map* from the CerebrA atlas and the ICBM
2009c Nonlinear Symmetric tissue maps.

The output is a single ``int16`` volume whose voxels hold a
:class:`TissueClass` code, in real anatomical scale (the
``MNI152NLin2009cSym`` template: 1 mm isotropic, RAS).  Every later stage only
ever looks at these class codes, never at template intensities, so the phantom
is fully under our control and reproducible.

Only the md5-pinned TemplateFlow files of ``anatomy_source`` are read, so
nothing subject- or licence-restricted is involved.

Extracerebral tissue (CSF gap, skull, scalp, background air) is *not* taken
from the template (whose averaged T1 has a blurred skull and stops at the
medulla); it is synthesised as clean concentric shells grown outward from the
brain mask with a Euclidean distance transform.  Sharp shell edges are exactly
what BET / SynthStrip need to behave like they do on real heads.
"""

from __future__ import annotations

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


#: The 31 Desikan-Killiany-Tourville cortical parcels of CerebrA, by the
#: ``name`` column of its label table (one entry per hemisphere upstream).
_CORTICAL_PARCELS = (
    "Caudal Anterior Cingulate",
    "Caudal Middle Frontal",
    "Cuneus",
    "Entorhinal",
    "Fusiform",
    "Inferior Parietal",
    "Inferior temporal",
    "Insula",
    "Isthmus Cingulate",
    "Lateral Occipital",
    "Lateral Orbitofrontal",
    "Lingual",
    "Medial Orbitofrontal",
    "Middle Temporal",
    "Paracentral",
    "Parahippocampal",
    "Pars Opercularis",
    "Pars Orbitalis",
    "Pars Triangularis",
    "Pericalcarine",
    "Postcentral",
    "Posterior Cingulate",
    "Precentral",
    "Precuneus",
    "Rostral Anterior Cingulate",
    "Rostral Middle Frontal",
    "Superior Frontal",
    "Superior Parietal",
    "Superior Temporal",
    "Supramarginal",
    "Transverse Temporal",
)

#: CerebrA label ``name`` -> tissue class. Every name of the label table must
#: be listed: an unknown one means the atlas changed upstream. ``None`` leaves
#: the label unconsumed (AIR), as the optic chiasm always was.
_CEREBRA_CLASSES = {
    **{name: TissueClass.CORTICAL_GM for name in _CORTICAL_PARCELS},
    "Thalamus": TissueClass.DEEP_GM,
    "Caudate": TissueClass.DEEP_GM,
    "Putamen": TissueClass.DEEP_GM,
    "Pallidum": TissueClass.DEEP_GM,
    "Accumbens Area": TissueClass.DEEP_GM,
    "Ventral Diencephalon": TissueClass.DEEP_GM,
    "Hippocampus": TissueClass.DEEP_GM,
    "Amygdala": TissueClass.DEEP_GM,
    "Basal Forebrain": TissueClass.DEEP_GM,
    "Lateral Ventricle": TissueClass.CSF_VENTRICLE,
    "Inferior Lateral Ventricle": TissueClass.CSF_VENTRICLE,
    "Third Ventricle": TissueClass.CSF_VENTRICLE,
    "Fourth Ventricle": TissueClass.CSF_VENTRICLE,
    "Cerebellum Gray Matter": TissueClass.CEREBELLUM_GM,
    "Vermal lobules I-V": TissueClass.CEREBELLUM_GM,
    "Vermal lobules VI-VII": TissueClass.CEREBELLUM_GM,
    "Vermal lobules VIII-X": TissueClass.CEREBELLUM_GM,
    "Cerebellum White Matter": TissueClass.CEREBELLUM_WM,
    "Brainstem": TissueClass.BRAINSTEM,
    "Optic Chiasm": None,
}

#: Motor cortex: fMRI activation source and CST origin.
_PRECENTRAL_NAME = "Precentral"

#: The template's field of view stops at the medulla: pad the grid so the
#: synthetic CSF/skull/scalp shells can close below the cerebellum.
_PAD_VOXELS = 30


def _read_cerebra_names(tsv_path: str) -> dict:
    """``label -> name`` from the CerebrA label table (tab separated)."""
    import csv

    with open(tsv_path, newline="") as handle:
        return {
            int(row["label"]): row["name"]
            for row in csv.DictReader(handle, delimiter="\t")
        }


def _cerebra_class_map(cerebra, names, gm, wm, csf, brain_mask, affine):
    """Tissue class map, precentral mask and affine from CerebrA + probseg.

    CerebrA labels cortex, deep grey matter, ventricles, cerebellum and
    brainstem, but has no cerebral white matter and no extra-axial CSF label.
    Those come from the ICBM 2009c GM/WM/CSF probabilistic segmentations:

    1. every labelled voxel takes the class of its label ``name``;
    2. cortical-parcel voxels where WM is more likely than GM become WM (an
       averaged template blurs the cortical ribbon into the white matter);
    3. unlabelled voxels inside the brain mask, with a total tissue
       probability above 0.5, take the dominant probseg class: WM -> WM,
       GM -> unparcellated cortex, CSF -> extra-axial CSF;
    4. the grid is padded by ``_PAD_VOXELS`` on every side, with the affine
       moved so world coordinates are unchanged.

    Returns ``(labels int16, precentral bool, affine)`` on the padded grid.
    """
    unknown = sorted(set(names.values()) - set(_CEREBRA_CLASSES))
    if unknown:
        raise ValueError(
            "CerebrA label name(s) with no phantom tissue class: %s"
            % ", ".join(unknown)
        )
    labels = np.full(cerebra.shape, TissueClass.AIR, dtype=np.int16)
    cortex = np.zeros(cerebra.shape, dtype=bool)
    precentral = np.zeros(cerebra.shape, dtype=bool)
    for label, name in names.items():
        cls = _CEREBRA_CLASSES[name]
        if cls is None:
            continue
        sel = cerebra == label
        labels[sel] = cls
        if cls == TissueClass.CORTICAL_GM:
            cortex |= sel
        if name == _PRECENTRAL_NAME:
            precentral |= sel

    to_wm = cortex & (wm > gm)
    labels[to_wm] = TissueClass.WM
    precentral &= ~to_wm

    free = (cerebra == 0) & brain_mask & ((gm + wm + csf) > 0.5)
    dominant = np.argmax(np.stack([gm, wm, csf]), axis=0)
    labels[free & (dominant == 0)] = TissueClass.CORTICAL_GM
    labels[free & (dominant == 1)] = TissueClass.WM
    labels[free & (dominant == 2)] = TissueClass.CSF_EXTRA

    pad = _PAD_VOXELS
    padded_affine = np.asarray(affine, dtype=float).copy()
    padded_affine[:3, 3] -= padded_affine[:3, :3] @ np.full(3, float(pad))
    return (
        np.pad(labels, pad, constant_values=TissueClass.AIR),
        np.pad(precentral, pad, constant_values=False),
        padded_affine,
    )


@dataclass
class TissueModel:
    """Result of stage A."""

    labels: np.ndarray  # int16, TissueClass codes
    affine: np.ndarray  # 4x4, voxel -> RAS (MNI152NLin2009cSym), padded template grid
    zooms: tuple  # mm, (1, 1, 1) for the template
    #: reference feature masks in the same grid, handy for later stages/tests
    precentral: np.ndarray  # bool, motor cortex
    cst: np.ndarray  # bool, cortico-spinal corridor
    #: (X, Y, Z, 3) unit fibre direction in RAS across the **whole white matter**,
    #: zero outside it.  Historically this held the CST corridor only; from
    #: phantom v9 it carries the principal direction of every fibre-bearing voxel
    #: -- the CST/AF/OR corridor tangents where a named bundle owns the voxel, and
    #: a smooth WM-background direction everywhere else -- so a whole-brain SLR has
    #: structure to register against.  The attribute name is kept (``cst_dir``) so
    #: ``deformation.py`` and ``sequences.py`` keep consuming it by name.
    cst_dir: np.ndarray = None
    #: bool, arcuate fasciculus corridor (fronto-temporal, bilateral)
    af: np.ndarray = None
    #: bool, optic radiation corridor (LGN -> calcarine, bilateral)
    optic_radiation: np.ndarray = None


def build_tissue_model(
    anatomy_files: dict | None = None,
    crop_margin_mm: float = 12.0,
    deform: bool = True,
) -> TissueModel:
    """Construct the phantom tissue class map from CerebrA + ICBM 2009c Sym.

    Parameters
    ----------
    anatomy_files : dict, optional
        ``key -> path`` as returned by
        :func:`~swane.tests.helpers.phantom.anatomy_source.resolve_anatomy_files`;
        resolved (and fetched if needed) when omitted.
    crop_margin_mm : float
        The padded template grid is cropped to the head bounding box plus this
        air margin, which cuts memory and render time for the coarse "fast"
        profile without changing world coordinates.  Set to a negative value to
        keep the full grid.
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

    from swane.tests.helpers.phantom.anatomy_source import resolve_anatomy_files

    files = anatomy_files or resolve_anatomy_files()
    ref_img = nib.load(files["cerebra"])
    cerebra = np.asarray(ref_img.dataobj).astype(np.int32)
    gm_prob, wm_prob, csf_prob = (
        np.asarray(nib.load(files[key]).dataobj, dtype=np.float32)
        for key in ("gm", "wm", "csf")
    )
    brain_mask = np.asarray(nib.load(files["mask"]).dataobj) > 0
    labels, precentral_base, affine = _cerebra_class_map(
        cerebra,
        _read_cerebra_names(files["tsv"]),
        gm_prob,
        wm_prob,
        csf_prob,
        brain_mask,
        ref_img.affine,
    )
    del gm_prob, wm_prob, csf_prob  # below, ``wm`` is only the bool WM mask
    zooms = tuple(float(z) for z in ref_img.header.get_zooms()[:3])

    brain = labels != TissueClass.AIR

    # --- synthesise extracerebral shells by distance from the brain mask ---
    # distance (mm) from the nearest brain voxel, isotropic 1 mm grid
    dist = ndi.distance_transform_edt(~brain, sampling=zooms)
    # subarachnoid CSF just outside the brain, then bone, then scalp/fat
    csf_gap = (dist > 0) & (dist <= 5)
    bone = (dist > 5) & (dist <= 9.5)
    diploe = (dist > 6.3) & (dist <= 8.2)  # marrow core inside the bone table
    scalp = (dist > 7.0) & (dist <= 12.0)

    labels[csf_gap] = TissueClass.CSF_EXTRA
    labels[bone] = TissueClass.SKULL
    labels[diploe] = TissueClass.DIPLOE
    labels[scalp] = TissueClass.SCALP
    # everything farther out stays AIR

    # --- feature overlays ------------------------------------------------
    precentral = precentral_base
    cst, cst_tan = _build_cst(brain, zooms, affine)
    af, af_tan = _build_tube_corridor(brain, _AF_WAYPOINTS_L, affine)
    orad, or_tan = _build_tube_corridor(brain, _OR_WAYPOINTS_L, affine)

    out = labels.copy()
    out[precentral] = TissueClass.PRECENTRAL_GM
    # CST runs through WM/brainstem; only stamp where it overlaps those tissues.
    cst_stampable = cst & np.isin(
        labels, [TissueClass.WM, TissueClass.BRAINSTEM, TissueClass.CEREBELLUM_WM]
    )
    out[cst_stampable] = TissueClass.CST
    # AF and OR are cerebral-WM tracts; keep them where they overlap WM.  They are
    # not stamped as a distinct tissue class (they stay WM in the label map): the
    # engine recognises them through the fibre direction field, not the labels, so
    # no new TissueClass / LUT entry is needed.
    wm = labels == TissueClass.WM
    af_stampable = af & wm
    or_stampable = orad & wm

    # Combined per-voxel fibre direction (stored on ``cst_dir``; see TissueModel).
    # A smooth whole-WM background gives a whole-brain SLR structure to register
    # against; each named corridor's curvature tangent then takes priority inside
    # its own voxels.  The support of the field is WM plus the corridor voxels the
    # CST adds outside WM (brainstem, cerebellar WM).
    fiber_dir = _wm_background_field(wm, affine, zooms)
    for mask, tan in (
        (cst_stampable, cst_tan),
        (af_stampable, af_tan),
        (or_stampable, or_tan),
    ):
        fiber_dir[mask] = tan[mask]
    fiber_support = wm | cst_stampable | af_stampable | or_stampable
    fiber_dir[~fiber_support] = 0.0

    venous = _build_venous_sinuses(brain, zooms, affine)
    out[venous & (out == TissueClass.CSF_EXTRA)] = TissueClass.VENOUS_SINUS

    # Warp the whole subject by the fixed smooth field *before* cropping, so the
    # head bounding box is measured on the deformed anatomy and nothing is
    # clipped. Labels, feature masks and the fibre directions move together.
    if deform:
        from swane.tests.helpers.phantom.deformation import deform_anatomy

        out, warped_masks, fiber_dir = deform_anatomy(
            out,
            {
                "precentral": precentral,
                "cst": cst_stampable,
                "af": af_stampable,
                "orad": or_stampable,
                "fiber_support": fiber_support,
            },
            fiber_dir,
            affine,
            zooms,
        )
        precentral = warped_masks["precentral"]
        cst_stampable = warped_masks["cst"]
        af_stampable = warped_masks["af"]
        or_stampable = warped_masks["orad"]

    precentral_out = precentral
    cst_out = cst_stampable
    af_out = af_stampable
    or_out = or_stampable
    if crop_margin_mm >= 0:
        out, affine, (sl, precentral_out, cst_out, af_out, or_out) = _crop_to_head(
            out,
            affine,
            zooms,
            crop_margin_mm,
            [precentral, cst_stampable, af_stampable, or_stampable],
        )
        fiber_dir = fiber_dir[sl]

    return TissueModel(
        labels=out,
        affine=affine,
        zooms=zooms,
        precentral=precentral_out,
        cst=cst_out,
        cst_dir=fiber_dir,
        af=af_out,
        optic_radiation=or_out,
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
# and were checked against the phantom built from CerebrA (see comment per waypoint).
# ``radius_mm`` is deliberately generous: the phantom bundle must *contain* the
# real tract so ROI-based tractography still intersects it.  Width is the safety
# margin - the waypoints themselves stay centred on the true course, since a
# wide-but-centred bundle is what keeps automatic ROIs on target.
_CST_WAYPOINTS_L = [
    # (R, A, S) mm, radius_mm; above each: segment -> lands in (CerebrA build)
    # M1 / precentral white matter -> CST corridor
    ((-34.0, -12.0, 48.0), 11.0),
    # corona radiata -> CST corridor
    ((-26.0, -14.0, 28.0), 10.0),
    # posterior limb internal capsule -> CST corridor
    ((-20.0, -14.0, 4.0), 8.0),
    # cerebral peduncle -> deep GM (ventral diencephalon)
    ((-12.0, -20.0, -14.0), 7.0),
    # basis pontis -> CST corridor (brainstem)
    ((-8.0, -22.0, -30.0), 6.5),
    # medullary pyramid -> CST corridor (brainstem)
    ((-5.0, -30.0, -48.0), 5.5),
]


# Arcuate fasciculus (AF): the dorsal, C-shaped fronto-temporal language tract.
# It runs from the inferior-frontal / precentral white matter, arches up and
# over the Sylvian fissure, then descends into the posterior superior/middle
# temporal white matter.  LEFT-side RAS(mm) waypoints; the right side is the
# x-mirror.  The waypoints stay lateral (|x| ~ 38-44 mm), sweep posteriorly in y
# and rise then fall in z, tracing the arch.  Radii are generous, as for the CST.
_AF_WAYPOINTS_L = [
    # (R, A, S) mm, radius_mm; above each: segment -> lands in (CerebrA build)
    # frontal terminus (IFG / precentral WM) -> cortical GM
    ((-38.0, 10.0, 26.0), 8.0),
    # ascending frontal limb -> WM
    ((-37.0, -2.0, 33.0), 7.5),
    # superior arch, above the Sylvian fissure -> CST corridor (crossing)
    ((-37.0, -18.0, 34.0), 7.0),
    # descending parieto-temporal limb -> WM
    ((-40.0, -34.0, 26.0), 7.0),
    # temporal terminus (posterior STG / MTG WM) -> WM
    ((-43.0, -44.0, 10.0), 7.5),
]

# Optic radiation (OR): lateral geniculate nucleus (posterolateral thalamus) ->
# occipital calcarine cortex, with Meyer's loop swinging anteriorly over the
# temporal horn before turning back.  LEFT-side RAS(mm) waypoints; right is the
# x-mirror.  The second waypoint is deliberately the most anterior and inferior
# point (Meyer's loop) before the tract sweeps posteriorly to the occipital pole.
_OR_WAYPOINTS_L = [
    # (R, A, S) mm, radius_mm; above each: segment -> lands in (CerebrA build)
    # LGN (posterolateral thalamus) -> deep GM (thalamus)
    ((-23.0, -26.0, 2.0), 6.0),
    # Meyer's loop (anterior temporal, inferior) -> WM
    ((-30.0, -20.0, -8.0), 6.0),
    # sagittal stratum along the temporal horn -> WM
    ((-34.0, -40.0, -6.0), 6.5),
    # posterior sweep toward the occipital lobe -> WM
    ((-30.0, -66.0, 2.0), 6.5),
    # calcarine / occipital terminus -> WM
    ((-18.0, -84.0, 6.0), 6.0),
]


def _build_tube_corridor(brain, waypoints_l, affine):
    """A bilateral smooth-tube corridor with a per-voxel curvature tangent.

    Shared machinery for every named bundle (CST, AF, OR): stamp a variable-radius
    tube through the LEFT ``waypoints_l`` and its x-mirror, in RAS millimetres so
    it is independent of the array axis order, and give each voxel the unit
    tangent of its nearest curve point.  A single global axis would make the
    bundle straight, and tractography would then leave it wherever the real
    tract bends; the local tangent keeps fibres inside the curve.
    """
    from scipy import ndimage as ndi

    corridor = np.zeros(brain.shape, dtype=bool)
    direction = np.zeros(brain.shape + (3,), dtype=np.float32)
    for mirror in (1.0, -1.0):
        pts = np.array(
            [[w[0][0] * mirror, w[0][1], w[0][2]] for w in waypoints_l],
            dtype=np.float64,
        )
        radii = np.array([w[1] for w in waypoints_l], dtype=np.float64)
        curve, curve_r = _resample_polyline(pts, radii, step_mm=0.5)
        tangents = _curve_tangents(curve)
        corridor |= _tube_ras(
            brain.shape, affine, curve, curve_r, tangents=tangents, dir_out=direction
        )

    corridor &= brain
    corridor = ndi.binary_closing(corridor, iterations=1)
    direction[~corridor] = 0.0
    return corridor, direction


def _wm_background_field(wm, affine, zooms):
    """A smooth, coherent principal direction for every white-matter voxel.

    RecoBundles runs a whole-brain SLR against the atlas *before* recognising
    any bundle, so a tractogram of a few isolated corridors registers
    arbitrarily and even the CST fails. The background field is what gives the
    whole-brain tractogram enough structure to register non-arbitrarily.

    Construction is derived only from the WM mask geometry (nothing subject- or
    atlas-derived): the Euclidean distance from the WM boundary is smoothed
    heavily (~6 mm) and its spatial gradient, rotated into RAS, is taken as the
    local principal direction. A low-frequency gradient is spatially coherent by
    construction (neighbouring voxels align), which is the requirement -- not
    biological exactness. Voxels where the smoothed gradient vanishes (the
    medial ridge, flat interior) inherit the nearest valid direction, so the
    field covers the whole WM without arbitrary constants breaking coherence.

    Returns an ``(X, Y, Z, 3)`` float32 unit field, zero outside ``wm``.
    """
    from scipy import ndimage as ndi

    wm = np.asarray(wm, dtype=bool)
    field = np.zeros(wm.shape + (3,), dtype=np.float32)
    if not wm.any():
        return field

    dist = ndi.distance_transform_edt(wm, sampling=zooms).astype(np.float64)
    sigma_vox = tuple(6.0 / float(z) for z in zooms)  # ~6 mm smoothing
    smooth = ndi.gaussian_filter(dist, sigma=sigma_vox)
    grad = np.gradient(smooth, *[float(z) for z in zooms])  # per-mm, index axes
    gidx = np.stack(grad, axis=-1)  # (X, Y, Z, 3) in index axes
    ras = gidx @ affine[:3, :3].T  # rotate the index gradient into RAS

    norm = np.linalg.norm(ras, axis=-1)
    valid = (norm > 1e-6) & wm
    if not valid.any():
        return field

    # Fill every WM voxel from the nearest voxel that has a defined gradient, so
    # ridge/flat voxels take a coherent neighbour direction rather than a hole.
    _, indices = ndi.distance_transform_edt(
        ~valid, return_distances=True, return_indices=True
    )
    filled = ras[tuple(indices)]  # (X, Y, Z, 3)
    fn = np.linalg.norm(filled, axis=-1, keepdims=True)
    fn[fn == 0] = 1.0
    unit = (filled / fn).astype(np.float32)
    field[wm] = unit[wm]
    return field


def _build_cst(brain, zooms, affine):
    """Cortico-spinal corridor following the real descending anatomy.

    The bundle is a smooth tube through anatomical waypoints (M1 -> corona
    radiata -> posterior limb of the internal capsule -> cerebral peduncle ->
    basis pontis -> medullary pyramid), built in RAS millimetres so it is
    independent of the array axis order.
    """
    return _build_tube_corridor(brain, _CST_WAYPOINTS_L, affine)


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


def _build_venous_sinuses(brain, zooms, affine):
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
