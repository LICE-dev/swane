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
        Thread class to scan a dicom folder and return dicom files ordered in patients, exams and series
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
                ds = pydicom.read_file(dicom_loc, force=True)

                # patient_id = self.clean_text(ds.get("PatientID", "NA"))
                patient_id = ds.get("PatientID", "na")
                #patient_id = DicomSearchWorker.clean_text(patient_id)
                if patient_id == "na":
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

                if patient_id not in self.dicom_tree:
                    self.dicom_tree[patient_id] = {}
                    self.series_positions[patient_id] = {}
                    if DEBUG:
                        print("New patient: " + str(patient_id))

                if study_instance_uid not in self.dicom_tree[patient_id]:
                    self.dicom_tree[patient_id][study_instance_uid] = {}
                    self.series_positions[patient_id][study_instance_uid] = {}
                    if DEBUG:
                        print("New study: " + str(study_instance_uid))

                if series_number not in self.dicom_tree[patient_id][study_instance_uid]:
                    self.dicom_tree[patient_id][study_instance_uid][series_number] = []
                    self.series_positions[patient_id][study_instance_uid][series_number] = [ds.get("SliceLocation"), 0]
                    if DEBUG:
                        print("New series: " + str(series_number) + " " + ds.SeriesDescription)

                self.dicom_tree[patient_id][study_instance_uid][series_number].append(dicom_loc)

                if self.series_positions[patient_id][study_instance_uid][series_number][0] == ds.get("SliceLocation"):
                    self.series_positions[patient_id][study_instance_uid][series_number][1] += 1
                    if DEBUG:
                        print("New volume for series: " + str(series_number))

                # if DEBUG:
                #     skip = True

            self.signal.sig_finish.emit(self)
        except:
            self.signal.sig_finish.emit(self)

    def get_patient_list(self):
        return list(self.dicom_tree.keys())

    def get_exam_list(self, patient: str) -> list[pydicom.uid.UID]:
        """
        Extract from dicom search the exams of specified patient and return their study_id
        Parameters
        ----------
        patient: str
            The patient id
        Returns
        -------
            A list of study_id
        """
        if patient not in self.dicom_tree:
            return []
        return list(self.dicom_tree[patient].keys())

    def get_series_list(self, patient: str, exam: pydicom.uid.UID) -> list[pydicom.valuerep.IS]:
        """
        Extract from dicom search the series of a specified exam of specified patient and return their series_id
        Parameters
        ----------
        patient: str
            The patient id
        exam: pydicom.uid.UID
            The exam id
        Returns
        -------
            A list of series_id
        """
        if patient not in self.dicom_tree:
            return []
        if exam not in self.dicom_tree[patient]:
            return []
        return list(self.dicom_tree[patient][exam].keys())

    def get_series_nvol(self, patient: str, exam: pydicom.uid.UID, series: pydicom.valuerep.IS) -> int:
        """
        Extract from dicom search the number of volumes of a specified series of a specified exam of specified patient and return their series_id
        Parameters
        ----------
        patient: str
            The patient id
        exam: pydicom.uid.UID
            The exam id
        series: pydicom.valuerep.IS
            The series id
        Returns
        -------
            An integer corresponding to the number of volumes of wanted series
        """
        return self.series_positions[patient][exam][series][1]

    def get_series_files(self, patient: str, exam: pydicom.uid.UID, series: pydicom.valuerep.IS) -> list[str]:
        """
        Extract from dicom search the dicom file path of a specified series of a specified exam of specified patient and return their series_id
        Parameters
        ----------
        patient: str
            The patient id
        exam: pydicom.uid.UID
            The exam id
        series: pydicom.valuerep.IS
            The series id
        Returns
        -------
            A list of series_id
        """
        if patient not in self.dicom_tree:
            return []
        if exam not in self.dicom_tree[patient]:
            return []
        if series not in self.dicom_tree[patient][exam]:
            return []
        return list(self.dicom_tree[patient][exam][series])

    def get_series_info(self, patient: str, exam: pydicom.uid.UID, series: pydicom.valuerep.IS) -> (list[str], str, str, str, int):
        """
        Extract information from dicom search the dicom file path of a specified series of a specified exam of specified patient
        Parameters
        ----------
        patient: str
            The patient id
        exam: pydicom.uid.UID
            The exam id
        series: pydicom.valuerep.IS
            The series id
        Returns
        -------
        image_list: list[str]
            A list of dicom files
        patient_name: str
            The patient name
        mod: str
            The exam modality
        series_description: str
            The series name
        vols: int
            The number of volumes

        """
        image_list = self.get_series_files(patient, exam, series)
        ds = pydicom.read_file(image_list[0], force=True)

        # Excludes series with less than 10 images unless they are siemens mosaics series
        if len(image_list) < 10 and hasattr(ds, 'ImageType') and "MOSAIC" not in ds.ImageType:
            return None

        mod = ds.Modality
        vols = self.get_series_nvol(patient, exam, series)
        patient_name = str(ds.PatientName)
        series_description = ds.SeriesDescription

        return image_list, patient_name, mod, series_description, vols
    