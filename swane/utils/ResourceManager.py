from math import ceil, floor
from psutil import virtual_memory, cpu_count
from swane.utils.platform_and_tools_utils import get_os_type


class ResourceManager:

    MINIMUM_CPU_MULTIPLIER = 1 / 3
    DEFAULT_CPU_MULTIPLIER = 1 / 2
    #: Shares of the total RAM of the Light, Balanced and High resource
    #: profiles. MAXIMUM_RAM_PERC is also the most RAM a subject tab can use.
    #: The limits apply to each subject tab, whatever the number of tabs.
    MINIMUM_RAM_PERC = 50
    DEFAULT_RAM_PERC = 70
    MAXIMUM_RAM_PERC = 90
    #: Most subjects analysed at the same time (subject tab limit).
    MAX_PARALLEL_SUBJECTS = 5

    SYNTH_STRIP_RAM_REQUIREMENT = {"mac": 30, "linux": 5, "other": 5, "windows": 5}
    SYNTH_MORPH_RAM_REQUIREMENT = {"mac": 20, "linux": 14, "other": 14, "windows": 14}
    SYNTH_SEG_RAM_REQUIREMENT = {"mac": 30, "linux": 14, "other": 14, "windows": 14}
    SYNTH_RECONALL_RAM_REQUIREMENT = {
        "mac": 20,
        "linux": 20,
        "other": 20,
        "windows": 20,
    }
    #: Measured peak RSS of the AntsRegistration node (fresh process, production
    #: schedules aff 2100/1200/1200/10 and SyN 100/70/50/20, Linux): Rigid/Affine
    #: 0.72-0.97 GB; SyN to the 1 mm templates 2.89-3.51 GB, the worst case being
    #: a 0.8 mm T1 to MNI152NLin2009cSym. The thread count barely matters (SyN
    #: 1 mm: 2.86 GB with 1 thread, 2.89 GB with 4). 4 GB = worst case + ~15%.
    ANTS_RAM_REQUIREMENT = {"mac": 4, "linux": 4, "other": 4, "windows": 4}
    #: antspynet brain extraction; fixed at 5 GB for now (revisit later).
    ANTSPYNET_RAM_REQUIREMENT = {"mac": 5, "linux": 5, "other": 5, "windows": 5}
    ATROPOS_RAM_REQUIREMENT = {"mac": 3, "linux": 3, "other": 3, "windows": 3}
    #: Minimum RAM to select the dipy tractography engine. It covers every dipy
    #: node's negotiated bottom rung so the workflow can run; the heavier nodes
    #: (motion, tracking) tune their parallelism/levers down to fit it, and
    #: DipyAtlasSLR fits its transform on a fixed subsample and streams the
    #: apply/write (measured tree-peak up to ~4.4 GB), so the one-way tissue
    #: classifier (no lever, linear in T1 voxels, ~5.7 GB) is the binding floor.
    #: DipySlrRamEstimator.STATIC_FALLBACK_GB reads this constant directly. See
    #: the dipy RAM report.
    DIPY_TRACTOGRAPHY_RAM_REQUIREMENT = {"mac": 6, "linux": 6, "other": 6, "windows": 6}
    #: Minimum RAM to select the nilearn (task) fMRI engine (covers antspynet
    #: BOLD extraction + first-level GLM).
    NILEARN_FMRI_RAM_REQUIREMENT = {"mac": 6, "linux": 6, "other": 6, "windows": 6}

    #: RAM scale for the Synth paths that do genuinely less work:
    #:
    #: - SynthSeg --fast (robust=False): scales its per-node mem_gb reservation
    #:   whenever --fast is used, i.e. in prerelease test_run AND in the
    #:   application when the subject's SynthSeg fast mode preference is on.
    #: - In prerelease test_run only: SynthMorph joint (steps=5) and Synth
    #:   recon-all (lighter iterations and SynthSeg --fast via the -expert
    #:   file) scale their reservation too.
    #:
    #: The prerelease gate (swane/tests/prerelease/capabilities.py
    #: _probe_synth_ram) lowers the same floors under test_run; the application's
    #: preference gates are never scaled. SynthStrip is never scaled. See the
    #: test_run/--fast branches in interfaces/utils.py (SynthMorphReg) and
    #: workflows/freesurfer_workflow.py.
    TEST_RUN_SYNTH_RAM_FACTOR = 0.7

    #: Cap applied to SynthStrip/SynthMorph/SynthSeg CPU thread count and node
    #: scheduler reservation when the user enables the "limit Synth tools CPU
    #: cores" preference (see interfaces/utils.py get_synth_cpu_config).
    SYNTH_CORE_LIMIT = 3

    @staticmethod
    def to_gb(bt: float) -> float:
        return round(bt / (1024**3), 2)

    @staticmethod
    def total_memory_gb() -> float:
        return ResourceManager.to_gb(virtual_memory().total)

    @staticmethod
    def get_minimum_ram() -> float:
        return ResourceManager.get_ram_by_perc(ResourceManager.MINIMUM_RAM_PERC)

    @staticmethod
    def get_maximum_ram() -> float:
        """Most RAM a subject tab can use."""
        return ResourceManager.get_ram_by_perc(ResourceManager.MAXIMUM_RAM_PERC)

    @staticmethod
    def get_minimum_subject_ram() -> float:
        """
        Smallest RAM allocation a subject tab can be given (the ram_gb range
        minimum): a fifth of the lightest profile, at least 0.1 GB.
        """
        return max(
            0.1,
            floor(
                ResourceManager.get_minimum_ram()
                / ResourceManager.MAX_PARALLEL_SUBJECTS
                * 10
            )
            / 10,
        )

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
    def atropos_ram_requirements():
        return ResourceManager.ATROPOS_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def dipy_tractography_ram_requirements():
        return ResourceManager.DIPY_TRACTOGRAPHY_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def nilearn_fmri_ram_requirements():
        return ResourceManager.NILEARN_FMRI_RAM_REQUIREMENT[get_os_type()]

    @staticmethod
    def get_min_synth_ram_requirement():
        return min(
            ResourceManager.synth_morph_ram_requirements(),
            ResourceManager.synth_reconall_ram_requirements(),
            ResourceManager.synth_strip_ram_requirements(),
        )

    @staticmethod
    def is_cuda():
        # Imported here: importing nipype at module level slows down GUI startup
        from nipype.utils.gpu_count import gpu_count

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
