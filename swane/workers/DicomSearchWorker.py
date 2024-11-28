import pydicom
import os
from PySide6.QtCore import Signal, QObject, QRunnable
from swane.nipype_pipeline.MainWorkflow import DEBUG
from swane.utils.DicomTree import DicomTree


class DicomSearchSignal(QObject):
    sig_loop = Signal(int)
    sig_finish = Signal(object)


class DicomSearchWorker(QRunnable):

    def __init__(self, dicom_dir: str):
        """
        Thread class to scan a dicom folder and return dicom files ordered in subjects, exams and series

        Parameters
        ----------
        dicom_dir: str
            The dicom folder to scan
        """
        super(DicomSearchWorker, self).__init__()
        if os.path.exists(os.path.abspath(dicom_dir)):
            self.dicom_dir = os.path.abspath(dicom_dir)
            self.unsorted_list = []
        self.signal = DicomSearchSignal()
        self.tree = DicomTree(dicom_dir)
        #self.dicom_tree = {}
        #self.series_positions = {}
        #self.multi_frame_series = {}

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
        try:
            if len(self.unsorted_list) == 0:
                self.load_dir()

            skip = False

            for dicom_loc in self.unsorted_list:
                self.signal.sig_loop.emit(1)

                if skip:
                    continue

                # read the file
                if not os.path.exists(dicom_loc):
                    continue
                ds = pydicom.dcmread(dicom_loc, force=True)

                subject_id = ds.get("PatientID", "na")
                if subject_id == "na":
                    continue

                series_number = ds.get("SeriesNumber", "NA")
                study_instance_uid = ds.get("StudyInstanceUID", "NA")

                # in GE la maggior parte delle ricostruzioni sono DERIVED\SECONDARY
                if (
                    hasattr(ds, "ImageType")
                    and "DERIVED" in ds.ImageType
                    and "SECONDARY" in ds.ImageType
                    and "ASL" not in ds.ImageType
                ):
                    continue
                # in GE e SIEMENS l'immagine anatomica di ASL è ORIGINAL\PRIMARY\ASL
                if (
                    hasattr(ds, "ImageType")
                    and "ORIGINAL" in ds.ImageType
                    and "PRIMARY" in ds.ImageType
                    and "ASL" in ds.ImageType
                ):
                    continue
                # in Philips e Siemens le ricostruzioni sono PROJECTION IMAGE
                if hasattr(ds, "ImageType") and "PROJECTION IMAGE" in ds.ImageType:
                    continue

                self.tree.add_subject(subject_id, str(ds.PatientName))
                self.tree.add_study(subject_id, study_instance_uid)
                dicom_series = self.tree.add_series(subject_id, study_instance_uid, series_number)

                multi_frame_series = False
                if "NumberOfFrames" in ds and int(ds.NumberOfFrames) > 1:
                    multi_frame_series = True

                dicom_series.add_dicom_loc(dicom_loc, multi_frame_series, ds.get("SliceLocation"))
                dicom_series.modality = ds.Modality
                if hasattr(ds, "SeriesDescription"):
                    dicom_series.description = ds.SeriesDescription
                else:
                    dicom_series.description = DicomSearchWorker.find_series_description(dicom_series.dicom_locs)

                #TODO: calcolare multiframe alla fine

            for subject in self.tree.dicom_subjects:
                for study in self.tree.dicom_subjects[subject].studies:
                    for series in self.tree.dicom_subjects[subject].studies[study]:
                        self.tree.dicom_subjects[subject].studies[study][series].refine_frame_number()
            self.signal.sig_finish.emit(self)
        except:
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
