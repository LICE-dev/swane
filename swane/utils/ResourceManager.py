from math import ceil, floor
from psutil import virtual_memory, cpu_count
from nipype.utils.gpu_count import gpu_count
from swane.utils.platform_and_tools_utils import get_os_type


class ResourceManager:

    MINIMUM_CPU_MULTIPLIER = 1 / 3
    DEFAULT_CPU_MULTIPLIER = 1 / 2
    MINIMUM_RAM = 5
    MINIMUM_RAM_PERC = 50
    MAXIMUM_RAM_PERC = 95
    DEFAULT_RAM_PERC = 70

    SYNTH_STRIP_RAM_REQUIREMENT = {"mac": 30, "linux": 5, "other": 5}
    SYNTH_MORPH_RAM_REQUIREMENT = {"mac": 20, "linux": 14, "other": 14}
    SYNTH_SEG_RAM_REQUIREMENT = {"mac": 30, "linux": 14, "other": 14}
    SYNTH_RECONALL_RAM_REQUIREMENT = {"mac": 20, "linux": 20, "other": 20}
    #: Placeholder pending real antspyx memory profiling: started at the same
    #: magnitude as SYNTH_MORPH_RAM_REQUIREMENT (Phase 1 CP-A, to confirm).
    ANTS_RAM_REQUIREMENT = {"mac": 5, "linux": 5, "other": 5}
    #: antspynet brain extraction; fixed at 5 GB for now (revisit later).
    ANTSPYNET_RAM_REQUIREMENT = {"mac": 5, "linux": 5, "other": 5}

    #: In prerelease test_run mode ONLY, the SynthSeg (--fast, robust=False) and
    #: SynthMorph (steps=5) paths do genuinely less work and use less RAM, so
    #: both their gate (whether the host may run them) and the per-node mem_gb
    #: reservation are scaled by this factor. SynthStrip and Synth recon-all get
    #: no such flag, so they are NOT scaled. The application (test_run=False)
    #: never applies this. See swane/tests/prerelease and the test_run branches
    #: in nodes/utils.py (SynthMorphReg) and workflows/freesurfer_workflow.py.
    TEST_RUN_SYNTH_RAM_FACTOR = 0.7

    #: Cap applied to SynthStrip/SynthMorph/SynthSeg CPU thread count and node
    #: scheduler reservation when the user enables the "limit Synth tools CPU
    #: cores" preference (see nodes/utils.py get_synth_cpu_config).
    SYNTH_CORE_LIMIT = 3

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
    def synth_seg_ram_requirements():
        return ResourceManager.SYNTH_SEG_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def synth_reconall_ram_requirements():
        return ResourceManager.SYNTH_RECONALL_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def ants_ram_requirements():
        return ResourceManager.ANTS_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def antspynet_ram_requirements():
        return ResourceManager.ANTSPYNET_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def get_min_synth_ram_requirement():
        return min(
            ResourceManager.synth_morph_ram_requirements(),
            ResourceManager.synth_reconall_ram_requirements(),
            ResourceManager.synth_strip_ram_requirements(),
        )

    @staticmethod
    def is_cuda():
        return gpu_count() > 0

    @staticmethod
    def get_min_cpu():
        return max(1, floor(cpu_count() * ResourceManager.MINIMUM_CPU_MULTIPLIER))

    @staticmethod
    def get_default_cpu():
        return max(1, floor(cpu_count() * ResourceManager.DEFAULT_CPU_MULTIPLIER))

    @staticmethod
    def get_max_cpu():
        return cpu_count()
