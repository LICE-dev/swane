"""The phantom exam: one series entry per phantom folder.

This module is the single place that decides *what* the phantom subject
contains - intensities, geometry, timing and the small inter-series
misalignment - so adding or retuning a modality never touches the render or
DICOM layers.

There is normally one entry per :class:`DataInputList` input, with two
deliberate exceptions: ``VENOUS_MR2`` has no default folder (the venous phases
ship as one 2-volume series), and a couple of extra ``venous_mr_split_*``
folders carry the same phases as separate single-volume series so the two-series
venous path is also testable.  ``FMRI_2`` is likewise left empty (two task runs
by design).

Two deliberate imperfections are baked in, because tests must be able to catch
them if a workflow stops fixing them:

* **Bias field** - ``T13D`` and ``FLAIR3D`` carry a strong low-frequency B1
  shading, so bias-field correction has something real to remove.
* **Misalignment** - every series except the ``T13D`` reference sits at a small
  rigid offset (a few mm / a few degrees), like a subject who moved between
  acquisitions.  If registration silently fails, the offset survives into the
  results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from swane.tests.helpers.phantom.sequences import (
    Plane,
    RestingDesign,
    SequenceSpec,
    TaskDesign,
    rigid_matrix,
)
from swane.tests.helpers.phantom.tissue import TissueClass as TC

# --------------------------------------------------------------------------- #
# Intensity look-up tables (arbitrary but physiologically ordered units)
# --------------------------------------------------------------------------- #
#: T1-weighted: WM bright > GM > CSF dark; fat (scalp/diploe) very bright.
LUT_T1 = {
    TC.CORTICAL_GM: 110,
    TC.PRECENTRAL_GM: 110,
    TC.DEEP_GM: 118,
    TC.WM: 160,
    TC.CST: 160,
    TC.CEREBELLUM_GM: 112,
    TC.CEREBELLUM_WM: 152,
    TC.BRAINSTEM: 150,
    TC.CSF_VENTRICLE: 28,
    TC.CSF_EXTRA: 30,
    TC.VENOUS_SINUS: 85,
    TC.SKULL: 12,
    TC.DIPLOE: 120,
    TC.SCALP: 175,
}

#: FLAIR: CSF nulled, GM slightly brighter than WM.
LUT_FLAIR = {
    TC.CORTICAL_GM: 150,
    TC.PRECENTRAL_GM: 150,
    TC.DEEP_GM: 140,
    TC.WM: 115,
    TC.CST: 115,
    TC.CEREBELLUM_GM: 148,
    TC.CEREBELLUM_WM: 118,
    TC.BRAINSTEM: 120,
    TC.CSF_VENTRICLE: 12,
    TC.CSF_EXTRA: 15,
    TC.VENOUS_SINUS: 70,
    TC.SKULL: 10,
    TC.DIPLOE: 150,
    TC.SCALP: 135,
}

#: T2: CSF very bright, GM > WM.
LUT_T2 = {
    TC.CORTICAL_GM: 170,
    TC.PRECENTRAL_GM: 170,
    TC.DEEP_GM: 150,
    TC.WM: 110,
    TC.CST: 110,
    TC.CEREBELLUM_GM: 168,
    TC.CEREBELLUM_WM: 112,
    TC.BRAINSTEM: 115,
    TC.CSF_VENTRICLE: 400,
    TC.CSF_EXTRA: 390,
    TC.VENOUS_SINUS: 120,
    TC.SKULL: 10,
    TC.DIPLOE: 190,
    TC.SCALP: 160,
}

#: Post-contrast T1: as T1 but vessels/dura enhance strongly.
LUT_MDC = dict(LUT_T1)
LUT_MDC[TC.VENOUS_SINUS] = 320

#: Diffusion b=0: T2-like contrast, no fat/bone signal to speak of.
LUT_DWI = {
    TC.CORTICAL_GM: 900,
    TC.PRECENTRAL_GM: 900,
    TC.DEEP_GM: 900,
    TC.WM: 1000,
    TC.CST: 1000,
    TC.CEREBELLUM_GM: 900,
    TC.CEREBELLUM_WM: 1000,
    TC.BRAINSTEM: 1000,
    TC.CSF_VENTRICLE: 1300,
    TC.CSF_EXTRA: 1250,
    TC.VENOUS_SINUS: 800,
    TC.SKULL: 80,
    TC.DIPLOE: 700,
    TC.SCALP: 600,
}

#: BOLD EPI: T2*-weighted, poor tissue contrast, bright CSF.
LUT_BOLD = {
    TC.CORTICAL_GM: 850,
    TC.PRECENTRAL_GM: 850,
    TC.DEEP_GM: 820,
    TC.WM: 780,
    TC.CST: 780,
    TC.CEREBELLUM_GM: 840,
    TC.CEREBELLUM_WM: 770,
    TC.BRAINSTEM: 760,
    TC.CSF_VENTRICLE: 1000,
    TC.CSF_EXTRA: 950,
    TC.VENOUS_SINUS: 700,
    TC.SKULL: 60,
    TC.DIPLOE: 500,
    TC.SCALP: 450,
}

#: ASL CBF map (ml/100g/min): GM ~4x WM, no signal outside the brain.
LUT_ASL = {
    TC.CORTICAL_GM: 60,
    TC.PRECENTRAL_GM: 60,
    TC.DEEP_GM: 55,
    TC.WM: 18,
    TC.CST: 18,
    TC.CEREBELLUM_GM: 58,
    TC.CEREBELLUM_WM: 18,
    TC.BRAINSTEM: 20,
    TC.CSF_VENTRICLE: 2,
    TC.CSF_EXTRA: 2,
    TC.VENOUS_SINUS: 5,
    TC.SKULL: 0,
    TC.DIPLOE: 3,
    TC.SCALP: 4,
}

#: FDG-PET uptake: GM ~4x WM.
LUT_PET = {
    TC.CORTICAL_GM: 8000,
    TC.PRECENTRAL_GM: 8000,
    TC.DEEP_GM: 7500,
    TC.WM: 2200,
    TC.CST: 2200,
    TC.CEREBELLUM_GM: 7000,
    TC.CEREBELLUM_WM: 2200,
    TC.BRAINSTEM: 2500,
    TC.CSF_VENTRICLE: 300,
    TC.CSF_EXTRA: 300,
    TC.VENOUS_SINUS: 900,
    TC.SKULL: 200,
    TC.DIPLOE: 500,
    TC.SCALP: 700,
}

#: Phase-contrast MRA, *anatomic* volume: PD-like, vessels not yet bright.
LUT_PC_ANAT = {
    TC.CORTICAL_GM: 120,
    TC.PRECENTRAL_GM: 120,
    TC.DEEP_GM: 120,
    TC.WM: 135,
    TC.CST: 135,
    TC.CEREBELLUM_GM: 120,
    TC.CEREBELLUM_WM: 135,
    TC.BRAINSTEM: 130,
    TC.CSF_VENTRICLE: 90,
    TC.CSF_EXTRA: 90,
    TC.VENOUS_SINUS: 140,
    TC.SKULL: 15,
    TC.DIPLOE: 180,
    TC.SCALP: 160,
}

#: Phase-contrast MRA, *velocity* volume: only flowing blood is bright.
LUT_PC_VENOUS = {
    TC.CORTICAL_GM: 20,
    TC.PRECENTRAL_GM: 20,
    TC.DEEP_GM: 20,
    TC.WM: 18,
    TC.CST: 18,
    TC.CEREBELLUM_GM: 20,
    TC.CEREBELLUM_WM: 18,
    TC.BRAINSTEM: 18,
    TC.CSF_VENTRICLE: 25,
    TC.CSF_EXTRA: 25,
    TC.VENOUS_SINUS: 450,
    TC.SKULL: 5,
    TC.DIPLOE: 15,
    TC.SCALP: 15,
}

# CT in Hounsfield units; stored with RescaleIntercept=-1024 (see catalog entry).
LUT_CT = {
    TC.CORTICAL_GM: 40,
    TC.PRECENTRAL_GM: 40,
    TC.DEEP_GM: 40,
    TC.WM: 28,
    TC.CST: 28,
    TC.CEREBELLUM_GM: 40,
    TC.CEREBELLUM_WM: 28,
    TC.BRAINSTEM: 32,
    TC.CSF_VENTRICLE: 6,
    TC.CSF_EXTRA: 6,
    TC.VENOUS_SINUS: 55,
    # Real cortical bone commonly reads 1500-1900 HU; kept comfortably above
    # the prerelease sweep's fixed skull_threshold test value (1500, see
    # tests/prerelease/plan.py) so that pass has real bone to segment, and
    # comfortably below the lowest electrode_threshold (2000) so it never
    # gets picked up as an SEEG electrode.
    TC.SKULL: 1900,
    TC.DIPLOE: 250,
    TC.SCALP: 50,
}


@dataclass
class SeriesEntry:
    """One DICOM series of the phantom exam."""

    input_name: str  # DataInputList value name -> folder name
    spec: SequenceSpec
    series_number: int
    description: str
    #: rigid displacement of the anatomy w.r.t. the scanner grid
    pose: object = None
    kind: str = "structural"  # structural | dwi | bold
    tr_s: float | None = None
    te_ms: float = 10.0
    flip_angle: float | None = None
    scanning_sequence: str | None = None
    image_type: tuple | None = None
    rescale_intercept: float = 0.0
    #: dwi
    n_directions: int = 6
    b_value: float = 1000.0
    #: bold
    n_vols: int = 0
    design: object = None  # TaskDesign | RestingDesign
    #: how many DICOM volumes this folder holds (venous MR packs 2)
    extra: dict = field(default_factory=dict)


def _misalign(rot, trans):
    """Small rigid offset - a subject who shifted between acquisitions."""
    return rigid_matrix(rot, trans)


def build_catalog(profile) -> list:
    """Return every series of the phantom exam for the given profile.

    ``profile`` supplies the voxel sizes (see
    :class:`swane.tests.helpers.phantom.dataset.PhantomProfile`).
    """
    iso3d = profile.iso_3d_mm
    iso2d_in = profile.in_plane_2d_mm
    slab2d = profile.slice_2d_mm
    dwi_mm = profile.dwi_mm
    bold_mm = profile.bold_mm
    ct_in = profile.ct_in_plane_mm
    ct_slice = profile.ct_slice_mm

    entries = []

    # --- reference: no pose offset, everything else is measured against it ---
    entries.append(
        SeriesEntry(
            input_name="t13d",
            series_number=1,
            description="3D T1w MPRAGE phantom",
            pose=None,
            tr_s=2.3,
            te_ms=3.0,
            flip_angle=9.0,
            scanning_sequence="GR",
            image_type=("ORIGINAL", "PRIMARY", "M", "NONE"),
            spec=SequenceSpec(
                "t13d",
                "MR",
                LUT_T1,
                in_plane_mm=iso3d,
                slice_mm=iso3d,
                noise_sigma=3.0,
                # strong shading: this is the bias-correction target
                bias_amp=0.45,
                clip_max=1023,
            ),
        )
    )

    entries.append(
        SeriesEntry(
            input_name="flair3d",
            series_number=2,
            description="3D FLAIR phantom",
            pose=_misalign((0.8, -1.2, 0.6), (1.5, -1.0, 0.8)),
            tr_s=5.0,
            te_ms=390.0,
            scanning_sequence="SE",
            spec=SequenceSpec(
                "flair3d",
                "MR",
                LUT_FLAIR,
                in_plane_mm=iso3d,
                slice_mm=iso3d,
                noise_sigma=3.5,
                # second bias-correction target
                bias_amp=0.40,
                clip_max=1023,
            ),
        )
    )

    entries.append(
        SeriesEntry(
            input_name="mdc",
            series_number=3,
            description="3D T1w post-contrast phantom",
            pose=_misalign((-0.6, 0.9, -1.0), (-1.2, 1.4, -0.9)),
            tr_s=2.3,
            te_ms=3.0,
            flip_angle=9.0,
            scanning_sequence="GR",
            spec=SequenceSpec(
                "mdc",
                "MR",
                LUT_MDC,
                in_plane_mm=iso3d,
                slice_mm=iso3d,
                noise_sigma=3.0,
                bias_amp=0.15,
                clip_max=1023,
            ),
        )
    )

    # --- 2D FLAIR in the three planes + coronal T2 ---
    for plane, input_name, rot, trans, number in (
        (Plane.AXIAL, "flair2d_tra", (1.0, 0.5, -0.8), (1.0, -1.5, 0.6), 4),
        (Plane.CORONAL, "flair2d_cor", (-1.1, 0.7, 0.9), (-0.8, 1.2, -1.3), 5),
        (Plane.SAGITTAL, "flair2d_sag", (0.7, -1.0, 1.1), (1.3, 0.9, -1.1), 6),
    ):
        entries.append(
            SeriesEntry(
                input_name=input_name,
                series_number=number,
                description="2D FLAIR %s phantom" % plane.value,
                pose=_misalign(rot, trans),
                tr_s=9.0,
                te_ms=120.0,
                scanning_sequence="SE",
                spec=SequenceSpec(
                    input_name,
                    "MR",
                    LUT_FLAIR,
                    in_plane_mm=iso2d_in,
                    slice_mm=slab2d,
                    plane=plane,
                    noise_sigma=4.0,
                    bias_amp=0.18,
                    clip_max=1023,
                ),
            )
        )

    # Coronal T2 is prescribed over the temporal lobes only, like a real
    # epilepsy protocol: the fsaverage temporal cortex spans A-P -81..+21 mm,
    # so a -90..+32 mm slab covers it with a margin while leaving the frontal
    # and occipital poles out (~2/3 of the brain's A-P extent).
    entries.append(
        SeriesEntry(
            input_name="t2_cor",
            series_number=7,
            description="2D T2 coronal phantom",
            pose=_misalign((0.9, -0.7, 1.0), (-1.4, 0.7, 1.2)),
            tr_s=4.5,
            te_ms=100.0,
            scanning_sequence="SE",
            spec=SequenceSpec(
                "t2_cor",
                "MR",
                LUT_T2,
                in_plane_mm=iso2d_in,
                slice_mm=slab2d,
                plane=Plane.CORONAL,
                noise_sigma=5.0,
                bias_amp=0.18,
                clip_max=1023,
                fov_ras={"A": (-90.0, 32.0)},
            ),
        )
    )

    # --- functional maps ---
    entries.append(
        SeriesEntry(
            input_name="asl",
            series_number=8,
            description="ASL CBF phantom",
            pose=_misalign((-0.9, 1.1, 0.7), (1.6, -1.3, 1.0)),
            tr_s=4.0,
            te_ms=12.0,
            scanning_sequence="GR",
            spec=SequenceSpec(
                "asl",
                "MR",
                LUT_ASL,
                in_plane_mm=profile.asl_mm,
                slice_mm=profile.asl_mm,
                noise_sigma=2.0,
                bias_amp=0.2,
                clip_max=4095,
            ),
        )
    )

    entries.append(
        SeriesEntry(
            input_name="pet",
            series_number=9,
            description="FDG PET phantom",
            pose=_misalign((1.2, -0.8, -1.1), (-1.7, 1.1, 1.4)),
            spec=SequenceSpec(
                "pet",
                "PT",
                LUT_PET,
                in_plane_mm=profile.pet_mm,
                slice_mm=profile.pet_mm,
                psf_fwhm_mm=6.0,
                noise_sigma=120.0,
                bias_amp=0.0,
                clip_max=32000,
            ),
        )
    )

    # --- venous MR --------------------------------------------------------
    # The workflow accepts the anatomic + angiographic phases either as ONE
    # series of two volumes (venous2_mr_dir=None -> it splits them) or as TWO
    # single-volume series (it merges them).  Both cases are provided in the
    # same subject:
    #   * venous_mr            : the 2-volume single series (case 1, imports as
    #                            VENOUS_MR with VENOUS_MR2 left empty)
    #   * venous_mr_split_anat : anatomic phase, 1 volume  \\ case 2: point
    #   * venous_mr_split_angio: angiographic phase, 1 volume / VENOUS_MR and
    #                            VENOUS_MR2 at these two folders
    # The angiographic phase suppresses the background and leaves only bright
    # vessels, i.e. a sparse, heavy-tailed intensity distribution, while the
    # anatomic phase is a filled tissue image. VenousCheck tells them apart from
    # that difference in either arrangement: the default KURTOSIS mode keys on
    # the heavy tail (used on the single 2-volume series) and the legacy SD/MEAN
    # modes on the lower spread/mean of the suppressed phase (SD is used on the
    # two-series arrangement); see tests/helpers/phantom/test_venous_separation.py.
    def _venous_spec(name, lut):
        return SequenceSpec(
            name,
            "MR",
            lut,
            in_plane_mm=iso3d,
            slice_mm=iso3d,
            noise_sigma=3.0,
            bias_amp=0.15,
            clip_max=1023,
        )

    entries.append(
        SeriesEntry(
            input_name="venous_mr",
            series_number=10,
            description="Venous MRA phase contrast (2 volumes)",
            pose=_misalign((0.6, 0.8, -0.9), (1.1, 1.3, -0.7)),
            tr_s=0.03,
            te_ms=7.0,
            scanning_sequence="GR",
            kind="venous_pair",
            spec=_venous_spec("venous_mr", LUT_PC_ANAT),
            extra={"second_lut": LUT_PC_VENOUS},
        )
    )
    # case-2 material: the same two phases as separate single-volume series.
    # Named off the DataInputList grid so they do not take part in the default
    # import; a two-series test wires them onto VENOUS_MR / VENOUS_MR2.
    entries.append(
        SeriesEntry(
            input_name="venous_mr_split_anat",
            series_number=11,
            description="Venous MRA anatomic phase (1 volume)",
            pose=_misalign((0.6, 0.8, -0.9), (1.1, 1.3, -0.7)),
            tr_s=0.03,
            te_ms=7.0,
            scanning_sequence="GR",
            spec=_venous_spec("venous_mr_split_anat", LUT_PC_ANAT),
        )
    )
    entries.append(
        SeriesEntry(
            input_name="venous_mr_split_angio",
            series_number=12,
            description="Venous MRA angiographic phase (1 volume)",
            pose=_misalign((0.9, 0.5, -1.1), (1.4, 1.0, -0.9)),
            tr_s=0.03,
            te_ms=7.0,
            scanning_sequence="GR",
            spec=_venous_spec("venous_mr_split_angio", LUT_PC_VENOUS),
        )
    )

    # --- venous CT: baseline + one-sided opacifications, to test the sum ------
    # The venous CT workflow reconstructs the opacified sinuses by combining a
    # non-contrast baseline with contrast scans.  Here the two contrast scans
    # opacify the dural sinuses on ONE side each (right, then left), so summing
    # baseline + right + left must recover bilateral opacification - and a bug
    # that drops one addend leaves a visibly one-sided result.  No arteries are
    # modelled (the phantom's vasculature is venous only).  VENOUS_CT4 is left
    # empty on purpose.
    def _ct_spec(name, side_override=None):
        return SequenceSpec(
            name,
            "CT",
            LUT_CT,
            in_plane_mm=ct_in,
            slice_mm=ct_slice,
            noise_sigma=12.0,
            noise_model="gaussian",
            bias_amp=0.0,
            background=-1000.0,
            clip_min=-1024.0,
            clip_max=3071.0,
            side_override=side_override,
        )

    OPACIFIED_HU = 260  # contrast-filled sinus lumen
    venous_ct_specs = [
        ("venous_ct", 13, "Venous CT baseline (no contrast)", None),
        (
            "venous_ct2",
            14,
            "Venous CT right-sided opacification",
            {"R": {TC.VENOUS_SINUS: OPACIFIED_HU}},
        ),
        (
            "venous_ct3",
            15,
            "Venous CT left-sided opacification",
            {"L": {TC.VENOUS_SINUS: OPACIFIED_HU}},
        ),
    ]
    for i, (name, number, desc, override) in enumerate(venous_ct_specs):
        entries.append(
            SeriesEntry(
                input_name=name,
                series_number=number,
                description=desc,
                pose=_misalign((0.5 + 0.2 * i, -0.6, 0.7), (0.9, -1.1 + 0.3 * i, 1.0)),
                rescale_intercept=-1024.0,
                spec=_ct_spec(name, override),
            )
        )

    # --- stereo-EEG CT: hyperdense electrodes ---
    entries.append(
        SeriesEntry(
            input_name="seeg_ct",
            series_number=16,
            description="Stereo-EEG CT phantom",
            pose=_misalign((-0.7, 0.6, 0.8), (1.2, 0.8, -1.1)),
            rescale_intercept=-1024.0,
            kind="seeg_ct",
            spec=SequenceSpec(
                "seeg_ct",
                "CT",
                LUT_CT,
                in_plane_mm=ct_in,
                slice_mm=ct_slice,
                noise_sigma=12.0,
                noise_model="gaussian",
                bias_amp=0.0,
                background=-1000.0,
                clip_min=-1024.0,
                clip_max=3071.0,
            ),
        )
    )

    # --- DTI ---
    entries.append(
        SeriesEntry(
            input_name="dti",
            series_number=17,
            description="DTI phantom",
            pose=_misalign((1.0, -1.3, 0.9), (-1.5, 1.2, 1.3)),
            kind="dwi",
            tr_s=6.0,
            te_ms=90.0,
            scanning_sequence="EP",
            image_type=("ORIGINAL", "PRIMARY", "DIFFUSION", "NONE"),
            n_directions=profile.dwi_directions,
            b_value=1000.0,
            spec=SequenceSpec(
                "dti",
                "MR",
                LUT_DWI,
                in_plane_mm=dwi_mm,
                slice_mm=dwi_mm,
                noise_sigma=15.0,
                bias_amp=0.12,
                clip_max=4095,
            ),
        )
    )

    # --- task fMRI: two motor runs with the two SWANe block designs ---------
    # Activation is contralateral: condition A is a right-hand task -> left
    # precentral cortex; condition B is a left-hand task -> right precentral.
    #   fmri_0: rArA      - single condition (A = right hand), WITH dummy
    #     volumes -- the real-world case a scanner leaves in, needing trim.
    #   fmri_1: rArBrArB  - A (right hand) alternating with B (left hand), with
    #     NO dummy volumes -- the real-world case where there is nothing to
    #     trim, so del_start_vols=del_end_vols=0 is the CORRECT declaration,
    #     not a lie. Fixed, not toggled per pass: every pass that loads both
    #     series exercises trimming real padding (fmri_0) and correctly
    #     declaring none (fmri_1) at once, rather than needing a separate
    #     "no trim" pass with padding it must then pretend isn't there (that
    #     mismatch used to desync the GLM and empty the activation maps).
    # FMRI_2 stays empty: the exam has two task runs by design.
    def _bold_spec(name):
        return SequenceSpec(
            name,
            "MR",
            LUT_BOLD,
            in_plane_mm=bold_mm,
            slice_mm=bold_mm,
            noise_sigma=12.0,
            bias_amp=0.12,
            clip_max=4095,
        )

    task_s = profile.bold_task_s
    rest_s = profile.bold_rest_s
    d_start = profile.bold_dummy_start
    d_end = profile.bold_dummy_end

    entries.append(
        SeriesEntry(
            input_name="fmri_0",
            series_number=18,
            description="Task fMRI motor rArA phantom",
            pose=_misalign((0.8, -0.9, 1.0), (1.3, -1.4, 0.9)),
            kind="bold",
            tr_s=profile.bold_tr_s,
            te_ms=30.0,
            scanning_sequence="EP",
            image_type=("ORIGINAL", "PRIMARY", "M", "NONE"),
            n_vols=d_start + profile.bold_task_core_vols + d_end,
            design=TaskDesign(
                paradigm="RARA",
                task_s=task_s,
                rest_s=rest_s,
                dummy_start=d_start,
                dummy_end=d_end,
            ),
            spec=_bold_spec("fmri_0"),
        )
    )
    entries.append(
        SeriesEntry(
            input_name="fmri_1",
            series_number=19,
            description="Task fMRI motor rArBrArB phantom (no dummy volumes)",
            pose=_misalign((1.0, -0.9, 1.2), (1.3, -1.4, 1.1)),
            kind="bold",
            tr_s=profile.bold_tr_s,
            te_ms=30.0,
            scanning_sequence="EP",
            image_type=("ORIGINAL", "PRIMARY", "M", "NONE"),
            # No dummy padding on this run (see comment above): the block design
            # starts at volume 0, so del_start_vols=del_end_vols=0 is correct.
            n_vols=profile.bold_task_dual_core_vols,
            design=TaskDesign(
                paradigm="RARBRARB",
                task_s=task_s,
                rest_s=rest_s,
                dummy_start=0,
                dummy_end=0,
            ),
            spec=_bold_spec("fmri_1"),
        )
    )

    entries.append(
        SeriesEntry(
            input_name="fmri_resting_state",
            series_number=20,
            description="Resting state fMRI phantom",
            pose=_misalign((-1.0, 0.9, -0.8), (-1.2, 1.5, 1.1)),
            kind="bold",
            tr_s=profile.bold_tr_s,
            te_ms=30.0,
            scanning_sequence="EP",
            image_type=("ORIGINAL", "PRIMARY", "M", "NONE"),
            n_vols=profile.bold_rest_vols,
            design=RestingDesign(n_networks=2, n_noise=1),
            spec=_bold_spec("fmri_resting_state"),
        )
    )

    return entries
