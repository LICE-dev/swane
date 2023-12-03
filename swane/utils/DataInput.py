from swane.config.PrefCategory import PrefCategory
from swane.config.config_enums import ImageModality

FMRI_NUM = 3


class DataInput(PrefCategory):
    def __init__(self, name: str, label: str = "", tooltip: str = "", image_modality: ImageModality = ImageModality.RM, optional: bool = False, wf_name: str = None, max_volumes: int = 1, min_volumes: int = 1):
        super().__init__(name, label)
        self.tooltip = tooltip
        self.image_modality = image_modality
        self.optional = optional
        self.loaded = False
        self.volumes = 0
        self.max_volumes = max_volumes
        self.min_volumes = min_volumes
        if wf_name is None:
            self.wf_name = self.name
        else:
            self.wf_name = wf_name

    def is_image_modality(self, image_modality_found):
        try:
            return self.image_modality == image_modality_found or self.image_modality.value.lower() == str(image_modality_found).lower()
        except:
            return False


