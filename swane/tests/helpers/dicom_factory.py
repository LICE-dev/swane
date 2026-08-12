"""Runtime generator for *phantom* DICOM files used by the test suite.

The goal is to avoid shipping real (even if anonymised) patient DICOM files in
the repository: every fixture is synthesised on the fly with :mod:`pydicom`.

Only the tags actually read by :class:`swane.workers.DicomSearchWorker` and
:class:`swane.utils.DicomTree` are populated, so the files stay tiny and no
pixel data is written by default.

Public helpers
--------------
- :func:`write_minimal_dicom` - single file, low level (kept for retro-compat).
- :func:`write_series`        - a whole series with an exact volume count.
- :func:`write_multiframe`    - a single enhanced/multi-frame DICOM.
"""

import datetime
import os

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    generate_uid,
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
)


def _new_dataset(path, file_meta=None):
    """Return an empty :class:`FileDataset` with sane, explicit encoding."""
    if file_meta is None:
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    dt = datetime.datetime.now()
    ds.ContentDate = dt.strftime("%Y%m%d")
    ds.ContentTime = dt.strftime("%H%M%S")
    return ds


def write_minimal_dicom(
    path,
    patient_id="PAT001",
    series_desc=None,
    image_type=None,
    number_of_frames=None,
    slice_location=0,
    study_uid=None,
    series_number=1,
    sop_uid=None,
    series_uid=None,
    patient_name=None,
    modality="MR",
):
    """Write a minimal DICOM file suitable for unit tests.

    Parameters
    ----------
    path : str
        Output file path.
    patient_id : str
        ``PatientID`` (also used as ``PatientName`` unless ``patient_name`` given).
    series_desc : str, optional
        ``SeriesDescription``.
    image_type : list | str, optional
        ``ImageType`` (e.g. ``["DERIVED", "SECONDARY"]``).
    number_of_frames : int, optional
        ``NumberOfFrames`` (marks the file as multi-frame when > 1).
    slice_location : float | int
        ``SliceLocation`` - used by ``DicomTree`` to count volumes.
    study_uid : str, optional
        ``StudyInstanceUID`` (generated when omitted).
    series_number : int
        ``SeriesNumber``.
    sop_uid : str, optional
        ``SOPInstanceUID`` (generated when omitted - keep it unique per file).
    series_uid : str, optional
        ``SeriesInstanceUID`` (generated when omitted).
    patient_name : str, optional
        ``PatientName`` (defaults to ``patient_id``).
    modality : str
        ``Modality`` (``MR``, ``CT``, ``PT``, ``XA`` ...).

    Returns
    -------
    str
        The path that was written.
    """
    ds = _new_dataset(path)
    ds.PatientID = patient_id
    ds.PatientName = patient_name if patient_name is not None else patient_id
    ds.StudyInstanceUID = study_uid if study_uid is not None else generate_uid()
    ds.SeriesInstanceUID = series_uid if series_uid is not None else generate_uid()
    ds.SeriesNumber = series_number
    ds.SOPInstanceUID = sop_uid if sop_uid is not None else generate_uid()
    ds.Modality = modality
    if series_desc is not None:
        ds.SeriesDescription = series_desc
    if image_type is not None:
        ds.ImageType = image_type
    if number_of_frames is not None:
        ds.NumberOfFrames = str(int(number_of_frames))

    ds.SliceLocation = slice_location

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    ds.save_as(path)
    return path


def write_series(
    dest_dir,
    *,
    n_slices,
    n_volumes=1,
    modality="MR",
    series_number=1,
    series_description=None,
    patient_id="PAT001",
    patient_name=None,
    study_uid=None,
    series_uid=None,
    image_type=None,
    filename_prefix="img",
    start_index=0,
):
    """Write a single DICOM series producing an *exact* volume count.

    ``n_slices`` distinct ``SliceLocation`` values are each repeated
    ``n_volumes`` times, so :meth:`DicomSeries.refine_frame_number` reports
    exactly ``n_volumes`` volumes and ``n_slices * n_volumes`` files.

    The volume count is independent of the order in which the worker walks the
    files: every slice position appears exactly ``n_volumes`` times, so whichever
    file is seen first, the number of files sharing its position is ``n_volumes``.

    Returns
    -------
    list[str]
        The paths written, in volume-major order.
    """
    os.makedirs(dest_dir, exist_ok=True)
    if study_uid is None:
        study_uid = generate_uid()
    if series_uid is None:
        series_uid = generate_uid()

    paths = []
    index = start_index
    for _volume in range(n_volumes):
        for slice_index in range(n_slices):
            path = os.path.join(dest_dir, f"{filename_prefix}_{index:04d}.dcm")
            write_minimal_dicom(
                path,
                patient_id=patient_id,
                patient_name=patient_name,
                series_desc=series_description,
                image_type=image_type,
                slice_location=float(slice_index),
                study_uid=study_uid,
                series_uid=series_uid,
                series_number=series_number,
                modality=modality,
            )
            paths.append(path)
            index += 1
    return paths


def write_multiframe(
    path,
    *,
    n_slices,
    n_volumes=1,
    modality="MR",
    series_number=1,
    series_description=None,
    patient_id="PAT_MF",
    patient_name=None,
    study_uid=None,
    series_uid=None,
):
    """Write a single enhanced/multi-frame DICOM with a known volume count.

    Builds ``PerFrameFunctionalGroupsSequence`` with ``n_slices * n_volumes``
    frames whose ``PlanePositionSequence`` repeats every ``n_slices`` frames,
    so :meth:`DicomSeries.refine_frame_number` reports ``n_volumes`` volumes.
    """
    ds = _new_dataset(path)
    ds.PatientID = patient_id
    ds.PatientName = patient_name if patient_name is not None else patient_id
    ds.StudyInstanceUID = study_uid if study_uid is not None else generate_uid()
    ds.SeriesInstanceUID = series_uid if series_uid is not None else generate_uid()
    ds.SeriesNumber = series_number
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = modality
    if series_description is not None:
        ds.SeriesDescription = series_description

    n_frames = n_slices * n_volumes
    ds.NumberOfFrames = str(n_frames)

    per_frame = Sequence()
    for _volume in range(n_volumes):
        for slice_index in range(n_slices):
            frame = Dataset()
            plane = Dataset()
            plane.ImagePositionPatient = [0.0, 0.0, float(slice_index)]
            frame.PlanePositionSequence = Sequence([plane])
            per_frame.append(frame)
    ds.PerFrameFunctionalGroupsSequence = per_frame

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    ds.save_as(path)
    return path
