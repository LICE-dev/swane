from enum import Enum

from swane.config.config_enums import ImageModality, PLANES
from swane.utils.DataInput import DataInput, FMRI_NUM


class DataInputList(Enum):
    T13D = DataInput(
        name='t13d',
        label='3D T1w'
    )
    FLAIR3D = DataInput(
        name='flair3d',
        label='3D Flair'
    )
    MDC = DataInput(
        name='mdc',
        label='Post-contrast 3D T1w'
    )
    VENOUS = DataInput(
        name='venous',
        label='Venous MRA - Phase contrast',
        tooltip='If you have anatomic and venous volumes in a single sequence, load it here. Otherwise, load one of the two volume (which one is not important)',
        max_volumes=2
    )
    VENOUS2 = DataInput(
        name=VENOUS.name+"2",
        label='Venous MRA - Second volume (optional)',
        tooltip='If you have anatomic and venous volumes in two different sequences, load the remaining volume here. Otherwise, leave this slot empty',
        wf_name='venous')
    DTI = DataInput(
        name='dti',
        label='Diffusion Tensor Imaging',
        max_volumes=-1,
        min_volumes=4
    )
    ASL = DataInput(
        name='asl',
        label='Arterial Spin Labeling',
        tooltip='CBF images from an ASL sequence'
    )
    PET = DataInput(
        name='pet',
        label='PET',
        image_modality=ImageModality.PET
    )

    _ignore_ = 'DataInputList i'
    DataInputList = vars()

    for i in PLANES:
        DataInputList["FLAIR2D_%s" % i.name] = DataInput(
            name='flair2d_%s' % i.name.lower(),
            label='2D Flair %s' % i.value,
            optional=True
        )

    for i in range(FMRI_NUM):
        DataInputList['FMRI_%d' % i] = DataInput(
            name='fmri_%d' % i,
            label='Task fMRI - Sequence %d' % (i+1),
            max_volumes=-1,
            min_volumes=4
        )

    def __str__(self):
        return self.value.name
