"""Reusable DICOM scenarios built on top of :mod:`dicom_factory`.

Every scenario is generated at runtime and ships with its *expected* metadata,
so tests assert against a single source of truth instead of scattered magic
numbers. A value of ``-1`` in an expectation means "do not check".
"""

import os
from dataclasses import dataclass

from pydicom.uid import generate_uid

from swane.tests.helpers.dicom_factory import (
    write_minimal_dicom,
    write_series,
    write_multiframe,
)


@dataclass
class Scenario:
    """A generated DICOM folder together with its expected scan result."""

    name: str
    path: str
    files: int          # total files walked by the worker (-1 = skip)
    subjects: int       # distinct PatientID (-1 = skip)
    studies: int        # studies of the first subject (-1 = skip)
    series: int         # series of the first study (-1 = skip)
    volumes: int        # volumes of the first series (-1 = skip)
    series_files: int   # dicom_locs of the first series (-1 = skip)


def build_dicom_tree(root):
    """Materialise every standard scenario under ``root``.

    Returns
    -------
    dict[str, Scenario]
        Keyed by scenario name (``SINGLE_VOL``, ``TWO_VOL`` ...).
    """
    os.makedirs(root, exist_ok=True)
    scenarios = {}

    # --- empty folder -----------------------------------------------------
    empty_dir = os.path.join(root, "empty_folder")
    os.makedirs(empty_dir, exist_ok=True)
    scenarios["EMPTY_FOLDER"] = Scenario(
        "EMPTY_FOLDER", empty_dir, 0, 0, 0, 0, 0, 0
    )

    # --- single volume: 11 slices, 1 volume -------------------------------
    single_dir = os.path.join(root, "singlevol")
    write_series(
        single_dir, n_slices=11, n_volumes=1,
        series_description="SINGLE", patient_id="P_SINGLE",
    )
    scenarios["SINGLE_VOL"] = Scenario(
        "SINGLE_VOL", single_dir, 11, 1, 1, 1, 1, 11
    )

    # --- two volumes: 5 slices x 2 volumes = 10 files ---------------------
    two_dir = os.path.join(root, "twovol")
    write_series(
        two_dir, n_slices=5, n_volumes=2,
        series_description="TWO", patient_id="P_TWO",
    )
    scenarios["TWO_VOL"] = Scenario(
        "TWO_VOL", two_dir, 10, 1, 1, 1, 2, 10
    )

    # --- multi volume: 3 slices x 4 volumes = 12 files --------------------
    multi_dir = os.path.join(root, "multivol")
    write_series(
        multi_dir, n_slices=3, n_volumes=4,
        series_description="MULTI", patient_id="P_MULTI",
    )
    scenarios["MULTI_VOL"] = Scenario(
        "MULTI_VOL", multi_dir, 12, 1, 1, 1, 4, 12
    )

    # --- non dicom files --------------------------------------------------
    nondicom_dir = os.path.join(root, "non_dicom_files")
    os.makedirs(nondicom_dir, exist_ok=True)
    for name in ("text1", "text2"):
        with open(os.path.join(nondicom_dir, name), "w", encoding="utf-8") as f:
            f.write("not a dicom")
    scenarios["NONDICOM"] = Scenario(
        "NONDICOM", nondicom_dir, 2, 0, 0, 0, 0, 0
    )

    # --- multi subject: two patients -------------------------------------
    multisubj_dir = os.path.join(root, "multisubj")
    os.makedirs(multisubj_dir, exist_ok=True)
    for patient in ("PA", "PB"):
        study_uid = generate_uid()
        for i in range(2):
            write_minimal_dicom(
                os.path.join(multisubj_dir, f"{patient.lower()}{i}.dcm"),
                patient_id=patient,
                series_desc="S_" + patient,
                study_uid=study_uid,
            )
    scenarios["MULTI_SUBJ"] = Scenario(
        "MULTI_SUBJ", multisubj_dir, 4, 2, -1, -1, -1, -1
    )

    # --- multi exam: one patient, two studies ----------------------------
    multiexam_dir = os.path.join(root, "multiexam")
    os.makedirs(multiexam_dir, exist_ok=True)
    for i in range(2):
        write_minimal_dicom(
            os.path.join(multiexam_dir, f"{i + 1}.dcm"),
            patient_id="P_EXAM",
            study_uid=generate_uid(),
        )
    scenarios["MULTI_EXAM"] = Scenario(
        "MULTI_EXAM", multiexam_dir, 2, 1, 2, -1, -1, 1
    )

    # --- multi-frame (enhanced) single file: 3 slices x 2 volumes --------
    multiframe_dir = os.path.join(root, "multiframe")
    os.makedirs(multiframe_dir, exist_ok=True)
    write_multiframe(
        os.path.join(multiframe_dir, "enhanced.dcm"),
        n_slices=3, n_volumes=2,
        series_description="ENHANCED", patient_id="P_MF",
    )
    scenarios["MULTIFRAME"] = Scenario(
        "MULTIFRAME", multiframe_dir, 1, 1, 1, 1, 2, 1
    )

    return scenarios
