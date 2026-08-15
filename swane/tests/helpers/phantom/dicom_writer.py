"""Stage C - serialise rendered volumes as DICOM series ``dcm2niix`` accepts.

Unlike :mod:`swane.tests.helpers.dicom_factory` (metadata-only files, enough for
:class:`swane.utils.DicomTree` to count volumes), these files carry real
``PixelData`` plus the full geometry and modality tags, so the whole
DICOM -> NIfTI -> FSL/FreeSurfer chain runs on them.

Points that matter, learned by running the real ``dcm2niix``:

* ``Manufacturer`` must be set, otherwise dcm2niix warns and guesses Philips.
* ``PatientPosition`` must be ``HFS``, otherwise the b-vector signs are wrong.
* Diffusion works through the *standard* tags ``(0018,9087) DiffusionBValue``
  and ``(0018,9089) DiffusionGradientOrientation`` - no vendor mosaic needed.
* A series needs **>= 10 slices**, else
  :meth:`swane.utils.DicomTree.DicomSeries.refine_frame_number` zeroes its frame
  count (unless it is flagged MOSAIC).
* 4D series are written volume-major with repeating ``SliceLocation`` so both
  dcm2niix and ``DicomTree`` recover the volume count.
"""

from __future__ import annotations

import datetime
import os

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    MRImageStorage,
    PositronEmissionTomographyImageStorage,
    generate_uid,
)

#: DICOM Modality -> SOP Class UID
_SOP_CLASS = {
    "MR": MRImageStorage,
    "CT": CTImageStorage,
    "PT": PositronEmissionTomographyImageStorage,
}

#: A vendor string keeps dcm2niix from guessing (and from expecting CSA blobs).
MANUFACTURER = "SWANE_PHANTOM"

MIN_SLICES = 10


def _ras_to_lps(affine: np.ndarray) -> np.ndarray:
    """DICOM patient space is LPS; NIfTI affines are RAS."""
    flip = np.diag([-1.0, -1.0, 1.0, 1.0])
    return flip @ affine


def _geometry(affine: np.ndarray):
    """Return (orientation cosines, direction vectors, spacings) in LPS.

    The volume is stored as ``data[i, j, k]``; slices run along ``k``, image
    columns along ``i`` and image rows along ``j``.
    """
    lps = _ras_to_lps(affine)
    col_dir = lps[:3, 0].astype(float)  # increasing column index (i)
    row_dir = lps[:3, 1].astype(float)  # increasing row index (j)
    slice_dir = lps[:3, 2].astype(float)  # increasing slice index (k)

    col_sp = float(np.linalg.norm(col_dir)) or 1.0
    row_sp = float(np.linalg.norm(row_dir)) or 1.0
    slice_sp = float(np.linalg.norm(slice_dir)) or 1.0

    col_u = col_dir / col_sp
    row_u = row_dir / row_sp
    slice_u = slice_dir / slice_sp

    # ImageOrientationPatient = [column cosines..., row cosines...]
    iop = [*col_u, *row_u]
    return iop, (col_u, row_u, slice_u), (col_sp, row_sp, slice_sp), lps


def _new_file_dataset(path, sop_class_uid):
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = sop_class_uid
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = sop_class_uid
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    now = datetime.datetime(2000, 1, 1, 12, 0, 0)  # fixed -> reproducible files
    ds.ContentDate = ds.StudyDate = ds.SeriesDate = now.strftime("%Y%m%d")
    ds.ContentTime = ds.StudyTime = ds.SeriesTime = now.strftime("%H%M%S")
    return ds


def write_volume_series(
    dest_dir: str,
    data: np.ndarray,
    affine: np.ndarray,
    *,
    modality: str = "MR",
    series_number: int = 1,
    series_description: str = "PHANTOM",
    patient_id: str = "PHANTOM",
    patient_name: str = "PHANTOM^SWANE",
    study_uid: str | None = None,
    series_uid: str | None = None,
    frame_uid: str | None = None,
    tr_s: float | None = None,
    te_ms: float = 10.0,
    flip_angle: float | None = None,
    scanning_sequence: str | None = None,
    image_type=None,
    bvals=None,
    bvecs=None,
    rescale_slope: float = 1.0,
    rescale_intercept: float = 0.0,
    filename_prefix: str = "img",
) -> list:
    """Write ``data`` (3D or 4D) as one DICOM series.

    Parameters
    ----------
    data : ndarray
        ``(X, Y, Z)`` or ``(X, Y, Z, T)``; slices are taken along ``Z`` and
        volumes along ``T``.
    affine : ndarray
        4x4 voxel -> RAS transform for the 3D grid.
    bvals, bvecs : sequence, optional
        When given (4D diffusion), the standard diffusion tags are written per
        volume so dcm2niix emits ``.bval``/``.bvec``.

    Returns
    -------
    list[str]
        Paths written, in acquisition order.
    """
    if modality not in _SOP_CLASS:
        raise ValueError("unsupported modality %r" % modality)
    data = np.asanyarray(data)
    if data.ndim == 3:
        data = data[..., None]
    if data.ndim != 4:
        raise ValueError("data must be 3D or 4D, got %dD" % data.ndim)

    n_i, n_j, n_k, n_t = data.shape
    if n_k < MIN_SLICES:
        raise ValueError(
            "series would have %d slices; SWANe's DicomTree needs at least %d"
            % (n_k, MIN_SLICES)
        )

    iop, (_, _, slice_u), (col_sp, row_sp, slice_sp), lps = _geometry(affine)
    origin = lps[:3, 3].astype(float)

    os.makedirs(dest_dir, exist_ok=True)
    study_uid = study_uid or generate_uid()
    series_uid = series_uid or generate_uid()
    frame_uid = frame_uid or generate_uid()
    sop_class = _SOP_CLASS[modality]

    # ``data`` holds real-world values (Hounsfield units for CT, arbitrary MR
    # intensity otherwise).  DICOM stores raw pixels that a viewer maps back with
    #   real = stored * RescaleSlope + RescaleIntercept
    # so the stored pixels must be the *inverse*: stored = (real - b) / m.  For
    # MR (m=1, b=0) this is a no-op; for CT (b=-1024) it shifts HU up into the
    # unsigned range, and reading back the intercept recovers the true HU - no
    # double counting.
    stored = (np.asarray(data, dtype=np.float64) - rescale_intercept) / rescale_slope
    stored = np.rint(stored)
    is_signed = bool(stored.min() < 0)
    pixel_data = stored.astype(np.int16 if is_signed else np.uint16)

    paths = []
    instance = 1
    for t in range(n_t):
        for k in range(n_k):
            path = os.path.join(dest_dir, "%s_%05d.dcm" % (filename_prefix, instance))
            ds = _new_file_dataset(path, sop_class)

            ds.PatientID = patient_id
            ds.PatientName = patient_name
            ds.PatientBirthDate = ""
            ds.PatientSex = "O"
            ds.PatientPosition = "HFS"  # required for correct bvec signs
            ds.Manufacturer = MANUFACTURER
            ds.ManufacturerModelName = "PhantomGenerator"
            ds.InstitutionName = "SWANE test suite"

            ds.StudyInstanceUID = study_uid
            ds.SeriesInstanceUID = series_uid
            ds.FrameOfReferenceUID = frame_uid
            ds.StudyID = "1"
            ds.AccessionNumber = ""
            ds.SeriesNumber = series_number
            ds.InstanceNumber = instance
            ds.Modality = modality
            ds.SeriesDescription = series_description
            ds.ProtocolName = series_description
            # Always emit ImageType: real scanners do, and downstream consumers
            # (e.g. the DICOM sequence classifier) assume it is present and
            # iterable.  Default to a plain original/primary acquisition.
            ds.ImageType = (
                list(image_type)
                if image_type is not None
                else [
                    "ORIGINAL",
                    "PRIMARY",
                ]
            )

            # --- geometry ---
            pos = origin + slice_u * (slice_sp * k)
            ds.ImageOrientationPatient = [float(v) for v in iop]
            ds.ImagePositionPatient = [float(v) for v in pos]
            ds.SliceLocation = float(np.dot(pos, slice_u))
            ds.PixelSpacing = [float(row_sp), float(col_sp)]
            ds.SliceThickness = float(slice_sp)
            ds.SpacingBetweenSlices = float(slice_sp)

            # --- pixel container ---
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.Rows = n_j
            ds.Columns = n_i
            ds.BitsAllocated = 16
            ds.BitsStored = 16
            ds.HighBit = 15
            ds.PixelRepresentation = 1 if is_signed else 0
            ds.RescaleSlope = rescale_slope
            ds.RescaleIntercept = rescale_intercept
            # pixel_array[row, col] == data[col, row] -> transpose the slice
            ds.PixelData = np.ascontiguousarray(pixel_data[:, :, k, t].T).tobytes()

            # --- modality specifics ---
            if modality == "MR":
                ds.MRAcquisitionType = "3D" if n_k > 60 else "2D"
                ds.ScanningSequence = scanning_sequence or "GR"
                ds.SequenceVariant = "NONE"
                ds.EchoTime = float(te_ms)
                ds.EchoNumbers = 1
                ds.MagneticFieldStrength = 3.0
                if flip_angle is not None:
                    ds.FlipAngle = float(flip_angle)
                if tr_s is not None:
                    ds.RepetitionTime = float(tr_s) * 1000.0
                if n_t > 1:
                    ds.NumberOfTemporalPositions = n_t
                    ds.TemporalPositionIdentifier = t + 1
            elif modality == "CT":
                ds.KVP = 120.0
                ds.RescaleType = "HU"
            elif modality == "PT":
                ds.Units = "BQML"

            # --- diffusion (standard tags; dcm2niix reads these) ---
            if bvals is not None and bvecs is not None:
                b = float(np.asarray(bvals)[t])
                g = np.asarray(bvecs)[t].astype(float)
                ds.DiffusionBValue = b
                ds.DiffusionGradientOrientation = [float(v) for v in g]
                ds.DiffusionDirectionality = "NONE" if b <= 0 else "DIRECTIONAL"

            ds.save_as(path, enforce_file_format=True)
            paths.append(path)
            instance += 1

    return paths
