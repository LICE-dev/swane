from enum import Enum
from swane.config.PrefCategory import PrefCategory
from swane.config.config_enums import ImageModality, PLANES

FMRI_NUM = 3


class DataInput(PrefCategory):
    def __init__(
        self,
        name: str,
        label: str = "",
        tooltip: str = "",
        image_modality: list[ImageModality] = [ImageModality.RM],
        optional: bool = False,
        workflow_name: str = None,
        max_volumes: int = 1,
        min_volumes: int = 1,
        parent_input=None
    ):
        super().__init__(name, label)
        self.tooltip = tooltip
        self.image_modality = image_modality
        self.optional = optional
        self.loaded = False
        self.volumes = 0
        self.max_volumes = max_volumes
        self.min_volumes = min_volumes
        self.parent_input: DataInput = parent_input
        if workflow_name is not None:
            self.workflow_name = workflow_name
        elif parent_input is not None:
            self.workflow_name = parent_input
        else:
            self.workflow_name = self.name

    def is_image_modality(self, image_modality_found: ImageModality) -> bool:
        try:
            if image_modality_found in self.image_modality:
                return True
            for this_modality in self.image_modality:
                if this_modality.value.lower() == str(image_modality_found).lower():
                    return True
        except:
            return False

        return False

    def get_modality_str(self):
        mod_string = ""
        for this_modality in self.image_modality:
            if mod_string == "":
                mod_string = this_modality.value.upper()
            else:
                mod_string += " or " + this_modality.value.upper()
        return mod_string


class DataInputList(Enum):
    T13D = DataInput(name="t13d", label="3D T1w")
    FLAIR3D = DataInput(name="flair3d", label="3D Flair")
    MDC = DataInput(name="mdc", label="Post-contrast 3D T1w")
    VENOUS = DataInput(
        name="venous",
        label="Venous MRA - Phase contrast",
        tooltip="If you have anatomic and venous volumes in a single sequence, load it here. Otherwise, load one of the two volume (which one is not important)",
        max_volumes=2,
        optional=True,
    )
    VENOUS2 = DataInput(
        name=VENOUS.name + "2",
        label="Venous MRA - Second volume (optional)",
        tooltip="If you have anatomic and venous volumes in two different sequences, load the remaining volume here. Otherwise, leave this slot empty",
        # workflow_name=VENOUS.name,
        parent_input="VENOUS"
    )
    VENOUS_CT = DataInput(
        name="venous_ct",
        label="Venous CT",
        tooltip="Load non contrast scan here and contrast scans in subsequent \"Venous CT - contrast\" slots",
        optional=True,
        image_modality=[ImageModality.CT, ImageModality.XA]
    )
    VENOUS_CT2 = DataInput(
        name=VENOUS_CT.name + "2",
        label="Venous CT - Contrast",
        parent_input="VENOUS_CT",
        image_modality=[ImageModality.CT, ImageModality.XA]
    )
    VENOUS_CT3 = DataInput(
        name=VENOUS_CT.name + "3",
        label="Venous CT - Contrast",
        parent_input="VENOUS_CT",
        image_modality=[ImageModality.CT, ImageModality.XA]
    )
    VENOUS_CT4 = DataInput(
        name=VENOUS_CT.name + "4",
        label="Venous CT - Contrast",
        parent_input="VENOUS_CT",
        image_modality=[ImageModality.CT, ImageModality.XA]
    )
    DTI = DataInput(
        name="dti", label="Diffusion Tensor Imaging", max_volumes=-1, min_volumes=4
    )
    ASL = DataInput(
        name="asl",
        label="Arterial Spin Labeling",
        tooltip="CBF images from an ASL sequence",
    )
    PET = DataInput(name="pet", label="PET", image_modality=[ImageModality.PET])
    SEEG_CT = DataInput(
        name="seeg_ct",
        label="Stereo-EEG CT",
        optional=True,
        image_modality=[ImageModality.CT]
    )

    # An Enum usually contains EVERY variable defined in its __init__, we want to ignore some used for loop only
    _ignore_ = "DataInputList i"
    DataInputList = vars()

    for i in PLANES:
        DataInputList["FLAIR2D_%s" % i.name] = DataInput(
            name="flair2d_%s" % i.name.lower(),
            label="2D Flair %s" % i.value,
            optional=True,
        )
    T2_COR = DataInput(name="t2_cor", label="2D T2 coronal", optional=True)

    for i in range(FMRI_NUM):
        DataInputList["FMRI_%d" % i] = DataInput(
            name="fmri_%d" % i,
            label="Task fMRI - Sequence %d" % (i + 1),
            optional=True,
            max_volumes=-1,
            min_volumes=4,
        )

    FMRI_RS = DataInput(
        name="fmri_resting_state",
        label="Resting state fMRI",
        optional=True,
        max_volumes=-1,
        min_volumes=4,
    )

    def __str__(self):
        return self.value.name
