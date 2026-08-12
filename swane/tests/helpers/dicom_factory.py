import datetime
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian, SecondaryCaptureImageStorage


def write_minimal_dicom(path, patient_id="PAT001", series_desc=None, image_type=None, number_of_frames=None, slice_location=0, study_uid=None, series_number=1, sop_uid=None):
    """Write a minimal DICOM file suitable for unit tests.

    Parameters
    - path: output file path
    - patient_id: PatientID and PatientName used by DicomSearchWorker
    - series_desc: optional SeriesDescription
    - image_type: optional ImageType (list or string)
    - number_of_frames: optional NumberOfFrames (int)
    - slice_location: optional SliceLocation (float/int)
    - study_uid: optional StudyInstanceUID (if None generated)
    - series_number: SeriesNumber (default 1)
    - sop_uid: optional SOPInstanceUID (if None generated)
    """
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientID = patient_id
    # also set PatientName because some code uses it
    ds.PatientName = patient_id
    ds.StudyInstanceUID = study_uid if study_uid is not None else generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = series_number
    ds.SOPInstanceUID = sop_uid if sop_uid is not None else generate_uid()
    ds.Modality = "MR"
    if series_desc is not None:
        ds.SeriesDescription = series_desc
    if image_type is not None:
        ds.ImageType = image_type
    if number_of_frames is not None:
        ds.NumberOfFrames = str(int(number_of_frames))

    # provide a slice location if requested
    ds.SliceLocation = slice_location

    # set timestamps
    dt = datetime.datetime.now()
    ds.ContentDate = dt.strftime('%Y%m%d')
    ds.ContentTime = dt.strftime('%H%M%S')

    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.save_as(path)
    return path
