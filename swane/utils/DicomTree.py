import pydicom


class DicomSeries:
    def __init__(self):
        self.dicom_locs = []
        self.frames = 0
        self.is_multi_frame = False
        self.multi_frame_loc = None
        self.first_position = None
        self.volumes = 1
        self.description = "Unnamed series"
        self.modality = None

    def add_dicom_loc(self, dicom_loc, is_multi_frame, slice_loc):
        if dicom_loc not in self.dicom_locs:
            self.dicom_locs.append(dicom_loc)
            if is_multi_frame:
                self.is_multi_frame = is_multi_frame
                self.multi_frame_loc = dicom_loc
            else:
                self.frames += 1
                if self.first_position is None:
                    self.first_position = slice_loc
                elif self.first_position == slice_loc:
                    self.volumes += 1

    def refine_frame_number(self):
        if self.is_multi_frame and self.multi_frame_loc is not None:
            ds = pydicom.dcmread(self.multi_frame_loc, force=True)
            for i, frame_group in enumerate(ds.PerFrameFunctionalGroupsSequence):
                if i == 0:
                    self.first_position = frame_group.PlanePositionSequence
                    self.volumes = 1
                    self.frames = int(ds.NumberOfFrames)
                elif self.first_position == frame_group.PlanePositionSequence:
                    self.volumes += 1
        elif self.frames < 10:
            ds = pydicom.dcmread(self.dicom_locs[0], force=True)
            if not hasattr(ds, "ImageType") or "MOSAIC" not in ds.ImageType:
                self.frames = 0



class DicomSubject:
    def __init__(self, subject_id: str, subject_name: str):
        self.subject_id = subject_id
        self.subject_name = subject_name
        self.studies = {}

    def add_study(self, study_instance_uid):
        if study_instance_uid not in self.studies:
            self.studies[study_instance_uid] = {}

    def add_series(self, study_instance_uid, series_number):
        if study_instance_uid not in self.studies:
            raise Exception("Study " + study_instance_uid + " not found")
        if series_number not in self.studies[study_instance_uid]:
            self.studies[study_instance_uid][series_number] = DicomSeries()
        return self.studies[study_instance_uid][series_number]

    def get_series_list(self, study_instance_uid: pydicom.uid.UID) -> list[pydicom.valuerep.IS]:
        if study_instance_uid not in self.studies:
            return []
        else:
            return list(self.studies[study_instance_uid].keys())

    def get_series(self, study_instance_uid: pydicom.uid.UID, series_number) -> DicomSeries:
        if study_instance_uid not in self.studies:
            return []
        elif series_number not in self.studies[study_instance_uid]:
            return []
        else:
            return self.studies[study_instance_uid][series_number]


class DicomTree:
    def __init__(self, dicom_dir: str):
        self.dicom_subjects = {}
        self.dicom_dir = dicom_dir

    def add_subject(self, subject_id, subject_name):
        if subject_id not in self.dicom_subjects:
            self.dicom_subjects[subject_id] = DicomSubject(subject_id, subject_name)

    def add_study(self, subject_id, study_instance_uid):
        if subject_id not in self.dicom_subjects:
            raise Exception("Subject " + subject_id + " not found")
        self.dicom_subjects[subject_id].add_study(study_instance_uid)

    def add_series(self, subject_id, study_instance_uid, series_number) -> DicomSeries:
        if subject_id not in self.dicom_subjects:
            raise Exception("Subject " + subject_id + " not found")
        return self.dicom_subjects[subject_id].add_series(study_instance_uid, series_number)

    def get_subject_list(self):
        return list(self.dicom_subjects.keys())

    def get_studies_list(self, subject: str) -> list[pydicom.uid.UID]:
        """
        Extract from dicom search the studies of specified subject and return their study_id

        Parameters
        ----------
        subject: str
            The subject id

        Returns
        -------
            A list of study_id
        """
        if subject not in self.dicom_subjects:
            return []
        return list(self.dicom_subjects[subject].studies.keys())

    def get_series_list(self, subject: str, study_instance_uid: pydicom.uid.UID) -> list[pydicom.valuerep.IS]:
        """
        Extract from dicom search the series of a specified studies of specified subject and return their series_id

        Parameters
        ----------
        subject: str
            The subject id
        study_instance_uid: pydicom.uid.UID
            The study id

        Returns
        -------
            A list of series_id
        """
        if subject not in self.dicom_subjects:
            return []
        return self.dicom_subjects[subject].get_series_list(study_instance_uid)

    def get_series(self, subject: str, study_instance_uid: pydicom.uid.UID, series_number) -> DicomSeries:
        if subject not in self.dicom_subjects:
            return None
        return self.dicom_subjects[subject].get_series(study_instance_uid, series_number)



