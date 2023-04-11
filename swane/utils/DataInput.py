import os


class DataInput:
    RM = 'mr'
    PET = 'pet'
    IMAGE_MODALITY_RENAME_LIST = {
        'PT': 'PET'
    }

    def __init__(self, name, label, image_modality=RM, optional=False, wf_name=None):
        self.name = name
        self.label = label
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

    PLANES = {'tra': 'transverse',
              'cor': 'coronal',
              'sag': 'sagittal',
              }
    FMRI_NUM = 3

    def __init__(self, dicom_dir=None):
        super(DataInputList, self).__init__()

        self.dicom_dir = dicom_dir

        self.append(DataInput(DataInputList.T13D, '3D T1w'))
        self.append(DataInput(DataInputList.FLAIR3D, '3D Flair'))
        self.append(DataInput(DataInputList.MDC, 'Post-contrast 3D T1w'))
        self.append(DataInput(DataInputList.VENOUS, 'Venous MRA - Phase contrast'))
        self.append(DataInput(DataInputList.VENOUS2, 'Venous MRA - Second phase', wf_name='venous'))
        self.append(DataInput(DataInputList.DTI, 'Diffusion Tensor Imaging', wf_name='dti_preproc'))
        self.append(DataInput(DataInputList.ASL, 'Arterial Spin Labeling'))
        self.append(DataInput(DataInputList.PET, 'PET', image_modality=DataInput.PET))

        for plane in DataInputList.PLANES:
            self.append(DataInput(DataInputList.FLAIR2D+'_'+plane, '2D Flair '+DataInputList.PLANES[plane], optional=True))

        for x in range(DataInputList.FMRI_NUM):
            self.append(DataInput(DataInputList.FMRI+'_%d' % x, 'Task fMRI - %d' % (x + 1)))

    def append(self, data_input):
        self[data_input.name] = data_input

    def is_ref_loaded(self):
        return self[DataInputList.T13D].loaded

    def get_dicom_dir(self, key):
        if key in self:
            return os.path.join(self.dicom_dir, key)
        return None






