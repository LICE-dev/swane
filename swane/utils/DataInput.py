import os


class DataInput:
    RM = 'mr'
    PET = 'pet'
    IMAGE_MODALITY_RENAME_LIST = {
        'PT': 'PET'
    }

    def __init__(self, name, label, tooltip, image_modality=RM, optional=False, wf_name=None):
        self.name = name
        self.label = label
        self.tooltip = tooltip
        self.image_modality = image_modality
        self.optional = optional
        self.loaded = False
        if wf_name is None:
            self.wf_name = self.name
        else:
            self.wf_name = wf_name

    def is_image_modality(self, image_modality_found):
        if image_modality_found in DataInput.IMAGE_MODALITY_RENAME_LIST:
            image_modality_found = DataInput.IMAGE_MODALITY_RENAME_LIST[image_modality_found]

        return self.image_modality.lower() == image_modality_found.lower()


class DataInputList(dict):

    T13D = 't13d'
    FLAIR3D = 'flair3d'
    MDC = 'mdc'
    VENOUS = 'venous'
    VENOUS2 = VENOUS+"2"
    DTI = 'dti'
    ASL = 'asl'
    PET = 'pet'
    FLAIR2D = 'flair2d'
    FMRI = 'fmri'

    input_list_string = {}
    input_list_string[T13D] = ['3D T1w', '']
    input_list_string[FLAIR3D] = ['3D Flair', '']
    input_list_string[MDC] = ['Post-contrast 3D T1w', '']
    input_list_string[VENOUS] = ['Venous MRA - Phase contrast', 'If you have anatomic and venous phases in a single sequence, load it here. Otherwise, load one of the two phases (which one is not important)']
    input_list_string[VENOUS2] = ['Venous MRA - Second phase (optional)', 'If you have anatomic and venous phases in two different sequences, load the remaining phase here. Otherwise, leave this slot empty']
    input_list_string[DTI] = ['Diffusion Tensor Imaging', '']
    input_list_string[ASL] = ['Arterial Spin Labeling', 'CBF images from an ASL sequence']
    input_list_string[PET] = ['PET', '']
    input_list_string[FLAIR2D] = ['2D Flair %s', '']
    input_list_string[FMRI] = ['Task fMRI - %d', '']

    PLANES = {'tra': 'transverse',
              'cor': 'coronal',
              'sag': 'sagittal',
              }
    FMRI_NUM = 3

    def __init__(self, dicom_dir=None):
        super(DataInputList, self).__init__()

        self.dicom_dir = dicom_dir

        self.append(DataInput(DataInputList.T13D, DataInputList.input_list_string[DataInputList.T13D][0], DataInputList.input_list_string[DataInputList.T13D][1]))
        self.append(DataInput(DataInputList.FLAIR3D, DataInputList.input_list_string[DataInputList.FLAIR3D][0], DataInputList.input_list_string[DataInputList.FLAIR3D][1]))
        self.append(DataInput(DataInputList.MDC, DataInputList.input_list_string[DataInputList.MDC][0], DataInputList.input_list_string[DataInputList.MDC][1]))
        self.append(DataInput(DataInputList.VENOUS, DataInputList.input_list_string[DataInputList.VENOUS][0], DataInputList.input_list_string[DataInputList.VENOUS][1]))
        self.append(DataInput(DataInputList.VENOUS2, DataInputList.input_list_string[DataInputList.VENOUS2][0], DataInputList.input_list_string[DataInputList.VENOUS2][1], wf_name='venous'))
        self.append(DataInput(DataInputList.DTI, DataInputList.input_list_string[DataInputList.DTI][0], DataInputList.input_list_string[DataInputList.DTI][1], wf_name='dti_preproc'))
        self.append(DataInput(DataInputList.ASL, DataInputList.input_list_string[DataInputList.ASL][0], DataInputList.input_list_string[DataInputList.ASL][1]))
        self.append(DataInput(DataInputList.PET, DataInputList.input_list_string[DataInputList.PET][0], DataInputList.input_list_string[DataInputList.PET][1], image_modality=DataInput.PET))

        for plane in DataInputList.PLANES:
            self.append(DataInput(DataInputList.FLAIR2D+'_'+plane, DataInputList.input_list_string[DataInputList.FLAIR2D][0] % DataInputList.PLANES[plane], DataInputList.input_list_string[DataInputList.FLAIR2D][1], optional=True))

        for x in range(DataInputList.FMRI_NUM):
            self.append(DataInput(DataInputList.FMRI+'_%d' % x, DataInputList.input_list_string[DataInputList.FMRI][0] % (x + 1), DataInputList.input_list_string[DataInputList.FMRI][1]))

    def append(self, data_input):
        self[data_input.name] = data_input

    def is_ref_loaded(self):
        return self[DataInputList.T13D].loaded

    def get_dicom_dir(self, key):
        if key in self:
            return os.path.join(self.dicom_dir, key)
        return None






