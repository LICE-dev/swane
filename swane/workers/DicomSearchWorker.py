import pydicom
import os
from PySide6.QtCore import Signal, QObject, QRunnable
from swane.nipype_pipeline.MainWorkflow import DEBUG


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
        self.dicom_tree = {}
        self.series_positions = {}

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
        forbidden_symbols = ["*", ".", ",", "\"", "\\", "/", "|", "[", "]", ":", ";", " "]
        for symbol in forbidden_symbols:
            # replace everything with an underscore
            string = string.replace(symbol, "_")
        return string.lower()

    def load_dir(self):
        """
        Generates the list of file to be scanned.
        """
        if self.dicom_dir is None or self.dicom_dir == "" or not os.path.exists(self.dicom_dir):
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
                if hasattr(ds, 'ImageType') and "DERIVED" in ds.ImageType and "SECONDARY" in ds.ImageType and "ASL" not in ds.ImageType:
                    continue
                # in GE e SIEMENS l'immagine anatomica di ASL è ORIGINAL\PRIMARY\ASL
                if hasattr(ds, 'ImageType') and "ORIGINAL" in ds.ImageType and "PRIMARY" in ds.ImageType and "ASL" in ds.ImageType:
                    continue
                # in Philips e Siemens le ricostruzioni sono PROJECTION IMAGE
                if hasattr(ds, 'ImageType') and "PROJECTION IMAGE" in ds.ImageType:
                    continue

                if subject_id not in self.dicom_tree:
                    self.dicom_tree[subject_id] = {}
                    self.series_positions[subject_id] = {}
                    if DEBUG:
                        print("New subject: " + str(subject_id))

                if study_instance_uid not in self.dicom_tree[subject_id]:
                    self.dicom_tree[subject_id][study_instance_uid] = {}
                    self.series_positions[subject_id][study_instance_uid] = {}
                    if DEBUG:
                        print("New study: " + str(study_instance_uid))

                if series_number not in self.dicom_tree[subject_id][study_instance_uid]:
                    self.dicom_tree[subject_id][study_instance_uid][series_number] = []
                    self.series_positions[subject_id][study_instance_uid][series_number] = [ds.get("SliceLocation"), 0]
                    if DEBUG:
                        print("New series: " + str(series_number) + " " + ds.SeriesDescription)

                self.dicom_tree[subject_id][study_instance_uid][series_number].append(dicom_loc)

                if self.series_positions[subject_id][study_instance_uid][series_number][0] == ds.get("SliceLocation"):
                    self.series_positions[subject_id][study_instance_uid][series_number][1] += 1
                    if DEBUG:
                        print("New volume for series: " + str(series_number))

                # if DEBUG:
                #     skip = True

            self.signal.sig_finish.emit(self)
        except:
            self.signal.sig_finish.emit(self)

    def get_subject_list(self):
        return list(self.dicom_tree.keys())

    def get_exam_list(self, subject: str) -> list[pydicom.uid.UID]:
        """
        Extract from dicom search the exams of specified subject and return their study_id
        Parameters
        ----------
        subject: str
            The subject id
        Returns
        -------
            A list of study_id
        """
        if subject not in self.dicom_tree:
            return []
        return list(self.dicom_tree[subject].keys())

    def get_series_list(self, subject: str, exam: pydicom.uid.UID) -> list[pydicom.valuerep.IS]:
        """
        Extract from dicom search the series of a specified exam of specified subject and return their series_id
        Parameters
        ----------
        subject: str
            The subject id
        exam: pydicom.uid.UID
            The exam id
        Returns
        -------
            A list of series_id
        """
        if subject not in self.dicom_tree:
            return []
        if exam not in self.dicom_tree[subject]:
            return []
        return list(self.dicom_tree[subject][exam].keys())

    def get_series_nvol(self, subject: str, exam: pydicom.uid.UID, series: pydicom.valuerep.IS) -> int:
        """
        Extract from dicom search the number of volumes of a specified series of a specified exam of specified subject and return their series_id
        Parameters
        ----------
        subject: str
            The subject id
        exam: pydicom.uid.UID
            The exam id
        series: pydicom.valuerep.IS
            The series id
        Returns
        -------
            An integer corresponding to the number of volumes of wanted series
        """
        return self.series_positions[subject][exam][series][1]

    def get_series_files(self, subject: str, exam: pydicom.uid.UID, series: pydicom.valuerep.IS) -> list[str]:
        """
        Extract from dicom search the dicom file path of a specified series of a specified exam of specified subject and return their series_id
        Parameters
        ----------
        subject: str
            The subject id
        exam: pydicom.uid.UID
            The exam id
        series: pydicom.valuerep.IS
            The series id
        Returns
        -------
            A list of series_id
        """
        if subject not in self.dicom_tree:
            return []
        if exam not in self.dicom_tree[subject]:
            return []
        if series not in self.dicom_tree[subject][exam]:
            return []
        return list(self.dicom_tree[subject][exam][series])

    def get_series_info(self, subject: str, exam: pydicom.uid.UID, series: pydicom.valuerep.IS) -> (list[str], str, str, str, int):
        """
        Extract information from dicom search the dicom file path of a specified series of a specified exam of specified subject
        Parameters
        ----------
        subject: str
            The subject id
        exam: pydicom.uid.UID
            The exam id
        series: pydicom.valuerep.IS
            The series id
        Returns
        -------
        image_list: list[str]
            A list of dicom files
        subject_name: str
            The subject name
        mod: str
            The exam modality
        series_description: str
            The series name
        vols: int
            The number of volumes

        """
        image_list = self.get_series_files(subject, exam, series)
        ds = pydicom.dcmread(image_list[0], force=True)

        # Excludes series with less than 10 images unless they are siemens mosaics series
        if len(image_list) < 10 and hasattr(ds, 'ImageType') and "MOSAIC" not in ds.ImageType:
            return None, None, None, None, None

        mod = ds.Modality
        vols = self.get_series_nvol(subject, exam, series)
        subject_name = str(ds.PatientName)
        series_description = ds.SeriesDescription

        return image_list, subject_name, mod, series_description, vols
    