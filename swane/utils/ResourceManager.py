from math import ceil
from psutil import virtual_memory, cpu_count
from nipype.utils.gpu_count import gpu_count
from swane.config.config_enums import GlobalPrefCategoryList
from swane.utils.platform_and_tools_utils import get_os_type


class ResourceManager:

    MINIMUM_RAM = 5
    MINIMUM_RAM_PERC = 50
    MAXIMUM_RAM_PERC = 95
    DEFAULT_RAM_PERC = 70

    SYNTH_STRIP_RAM_REQUIREMENT = {"mac": 30, "linux": 5, "other": 5}
    SYNTH_MORPH_RAM_REQUIREMENT = {"mac": 14, "linux": 14, "other": 14}
    SYNTH_RECONALL_RAM_REQUIREMENT = {"mac": 20, "linux": 20, "other": 20}

    @staticmethod
    def to_gb(bt: float) -> float:
        return round(bt / (1024**3), 2)

    @staticmethod
    def total_memory_gb() -> float:
        return ResourceManager.to_gb(virtual_memory().total)

    @staticmethod
    def get_minimum_ram() -> float:
        minimum_ram = max(
            ResourceManager.MINIMUM_RAM,
            ResourceManager.get_ram_by_perc(ResourceManager.MINIMUM_RAM_PERC),
        )
        return min(minimum_ram, ResourceManager.total_memory_gb())

    @staticmethod
    def get_maximum_ram() -> float:
        maximum_ram = max(
            ResourceManager.MINIMUM_RAM,
            ResourceManager.get_ram_by_perc(ResourceManager.MAXIMUM_RAM_PERC),
        )
        return min(maximum_ram, ResourceManager.total_memory_gb())

    @staticmethod
    def get_ram_by_perc(perc: int) -> float:
        ram_by_perc = virtual_memory().total * perc / 100
        return ResourceManager.to_gb(ram_by_perc)

    @staticmethod
    def get_ram_by_perc_safe(perc: int) -> float:
        ram_by_perc = ResourceManager.get_ram_by_perc(perc)
        if ram_by_perc > ResourceManager.get_maximum_ram():
            ram_by_perc = ResourceManager.get_maximum_ram()
        elif ram_by_perc < ResourceManager.get_minimum_ram():
            ram_by_perc = ResourceManager.get_minimum_ram()
        return ram_by_perc

    @staticmethod
    def get_default_ram():
        return ResourceManager.get_ram_by_perc_safe(ResourceManager.DEFAULT_RAM_PERC)

    @staticmethod
    def synth_strip_ram_requirements():
        return ResourceManager.SYNTH_STRIP_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def synth_morph_ram_requirements():
        return ResourceManager.SYNTH_MORPH_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def synth_reconall_ram_requirements():
        return ResourceManager.SYNTH_RECONALL_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    # We need config argument to support prefenrence loop
    def is_cuda(config):
        return gpu_count() > 0

    @staticmethod
    def suggested_max_cpu():
        # TODO: ricontrolliamo questa!
        try:
            return max(
                ceil(min(cpu_count() / 2, ResourceManager.total_memory_gb() / 3)), 1
            )
        except:
            return 1

    @staticmethod
    def max_cpu():
        return cpu_count()
