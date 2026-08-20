import pydicom
import os
from swane.utils.qt_compat import Signal, QObject, QRunnable
from swane.utils.DicomTree import DicomTree

# Import dicom_sequence_classifier lazily inside find_series_classification to
# avoid hard dependency at module import time (helps tests and environments
# where the package may not be fully available).


class DicomSearchSignal(QObject):
    sig_loop = Signal(int)
    sig_finish = Signal(object)


class DicomSearchWorker(QRunnable):

    def __init__(self, dicom_dir: str, classify: bool = False):
        """
        Thread class to scan a dicom folder and return dicom files ordered in subjects, exams and series

        Parameters
        ----------
        dicom_dir: str
            The dicom folder to scan
        classify: bool
            Try to classify dicom images in series. Default is False
        """
        super(DicomSearchWorker, self).__init__()
        # Always initialize the attributes: if the directory does not exist
        # dicom_dir is set to None (load_dir/run handle it gracefully) instead
        # of leaving the attributes undefined and raising AttributeError later.
        self.unsorted_list = []
        if os.path.exists(os.path.abspath(dicom_dir)):
            self.dicom_dir = os.path.abspath(dicom_dir)
        else:
            self.dicom_dir = None
        self.signal = DicomSearchSignal()
        self.tree = DicomTree(dicom_dir)
        self.error_message = []
        self.classify = classify

    @staticmethod
    def clean_text(string: str) -> str:
        """
        Remove forbidden characters from a string

        Parameters
        ----------
        string: str
            The string to clean.

        Returns
            The cleaned string in lower case.
        -------

        """
        # clean and standardize text descriptions, which makes searching files easier
        forbidden_symbols = [
            "*",
            ".",
            ",",
            '"',
            "\\",
            "/",
            "|",
            "[",
            "]",
            ":",
            ";",
            " ",
        ]
        for symbol in forbidden_symbols:
            # replace everything with an underscore
            string = string.replace(symbol, "_")
        return string.lower()

    def load_dir(self):
        """
        Generates the list of file to be scanned.
        """
        if (
            self.dicom_dir is None
            or self.dicom_dir == ""
            or not os.path.exists(self.dicom_dir)
        ):
            return
        self.unsorted_list = []
        for root, dirs, files in os.walk(self.dicom_dir):
            for file in files:
                self.unsorted_list.append(os.path.join(root, file))

    def get_files_len(self):
        """
        The number of file to be scanned
        """
        try:
            return len(self.unsorted_list)
        except:
            return 0

    def run(self):
        if len(self.unsorted_list) == 0:
            self.load_dir()

        for dicom_loc in self.unsorted_list:
            self.signal.sig_loop.emit(1)

            # Each file is scanned in isolation: a single unreadable or corrupt
            # dicom must be skipped without aborting the whole folder scan.
            try:
                # read the file
                if not os.path.exists(dicom_loc):
                    continue
                ds = pydicom.dcmread(dicom_loc, force=True)

                subject_id = ds.get("PatientID", "na")
                if subject_id == "na":
                    continue

                series_number = ds.get("SeriesNumber", "NA")
                study_instance_uid = ds.get("StudyInstanceUID", "NA")
                modality = ds.get("Modality", "")
                image_type = ds.get("ImageType", None)

                # in GE most reconstructions are DERIVED\SECONDARY
                if (
                    image_type is not None
                    and modality != "XA"  # xperct images are derived
                    and "DERIVED" in image_type
                    and "SECONDARY" in image_type
                    and "ASL" not in image_type
                ):
                    if image_type not in self.error_message:
                        self.error_message.append(image_type)
                    continue
                # in GE and SIEMENS the anatomic ASL image is ORIGINAL\PRIMARY\ASL
                if (
                    image_type is not None
                    and "ORIGINAL" in image_type
                    and "PRIMARY" in image_type
                    and "ASL" in image_type
                ):
                    if image_type not in self.error_message:
                        self.error_message.append(image_type)
                    continue
                # in Philips and Siemens reconstructions are PROJECTION IMAGE
                if image_type is not None and "PROJECTION IMAGE" in image_type:
                    if image_type not in self.error_message:
                        self.error_message.append(image_type)
                    continue

                self.tree.add_subject(subject_id, str(ds.get("PatientName", "")))
                self.tree.add_study(subject_id, study_instance_uid)
                dicom_series = self.tree.add_series(
                    subject_id, study_instance_uid, series_number
                )

                multi_frame_series = False
                if "NumberOfFrames" in ds and int(ds.NumberOfFrames) > 1:
                    multi_frame_series = True

                sop_uid = None
                if "SOPInstanceUID" in ds:
                    sop_uid = ds.SOPInstanceUID

                dicom_series.add_dicom_loc(
                    dicom_loc, multi_frame_series, ds.get("SliceLocation"), sop_uid, ds
                )
                dicom_series.modality = modality
                if dicom_series.description == "Not named":
                    if hasattr(ds, "SeriesDescription"):
                        dicom_series.description = ds.SeriesDescription
                    else:
                        dicom_series.description = (
                            DicomSearchWorker.find_series_description(
                                dicom_series.dicom_locs
                            )
                        )

                # TODO: calculate multiframe at the end

                if self.classify and dicom_series.classification == "Not classified":
                    dicom_series.classification = (
                        DicomSearchWorker.find_series_classification(ds)
                    )
            except Exception:
                # unreadable/corrupt file: skip it and keep scanning the rest
                continue

        try:
            for subject in self.tree.dicom_subjects:
                for study in self.tree.dicom_subjects[subject].studies:
                    for series in self.tree.dicom_subjects[subject].studies[study]:
                        self.tree.dicom_subjects[subject].studies[study][
                            series
                        ].refine_frame_number()
        except Exception:
            pass

        self.signal.sig_loop.emit(1)
        self.signal.sig_finish.emit(self)

    @staticmethod
    def find_series_description(image_list: list[str]) -> str:
        """
        Extract the description of the dicom series searching among all the series images.
        The description is equal to:
        - the SeriesDescription tag, if any in one of the image list
        - otherwise, None (unnamed_series)

        Parameters
        ----------
        image_list: list[str]
            The dicom file list to check

        Returns
        -------
        str
            The dicom series description

        """

        for image in image_list:
            ds = pydicom.dcmread(image, force=True)

            if hasattr(ds, "SeriesDescription"):
                return ds.SeriesDescription
        return "Unnamed series"

    @staticmethod
    def find_series_classification(ds) -> str:
        """
        Analyses the dicom using dicom_sequence_classifier to attempt an automatic dicom series classification.

        Parameters
        ----------
        ds:
            The dicom dataset to check

        Returns
        -------
        str
            The dicom series classification

        """

        # Import locally so a missing dicom_sequence_classifier package (e.g. in
        # a bare test environment) degrades gracefully to "Unknown" instead of
        # breaking module import.
        try:
            from dicom_sequence_classifier import extract_metadata, classify_dicom
        except ImportError:
            return "Unknown"

        # The classifier is best-effort and third-party: on unusual (but valid)
        # DICOM it can raise - e.g. it assumes ImageType is always present and
        # iterable. A classification failure must never abort the whole folder
        # scan, so any error degrades to "Unknown" and the import continues.
        try:
            meta = extract_metadata(ds)
            classification = classify_dicom(meta)
        except Exception:
            return "Unknown"

        if classification != "NOT MR":
            return classification

        return "Unknown"
