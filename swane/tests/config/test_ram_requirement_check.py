"""Load-time re-validation of preferences that need a minimum RAM.

An engine option (or the Synth recon-all switch) whose RAM requirement no
longer fits ``ram_gb`` must not stay selected: its node would reserve more than
the workflow budget and the plugin's prerun check would refuse every workflow.
"""

from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import (
    DeskullEngine,
    FmriEngine,
    FreesurferStep,
    GlobalPrefCategoryList,
    SegmentationEngine,
)
from swane.utils.DataInputList import DataInputList

SYNTH = GlobalPrefCategoryList.SYNTH
PERF = GlobalPrefCategoryList.PERFORMANCE


class _Deps:
    """Every dependency available except, optionally, FSL."""

    def __init__(self, fsl: bool = True):
        self._fsl = fsl

    def is_fsl(self):
        return self._fsl

    def __getattr__(self, name):
        if name.startswith("is_"):
            return lambda: True
        raise AttributeError(name)


def _global(tmp_path, ram_gb: float, **synth) -> ConfigManager:
    config = ConfigManager(global_base_folder=str(tmp_path))
    config[PERF]["ram_gb"] = str(ram_gb)
    for key, value in synth.items():
        config[SYNTH][key] = value
    return config


def test_engines_above_ram_are_reset_to_an_engine_that_fits(tmp_path):
    # ANTSPYNET needs 5 GB, Atropos 3 GB, nilearn fMRI 6 GB; the FSL engines
    # have no RAM requirement.
    config = _global(
        tmp_path,
        2.5,
        deskull_engine=DeskullEngine.ANTSPYNET.name,
        segmentation_engine=SegmentationEngine.ANTS.name,
        fmri_engine=FmriEngine.NILEARN.name,
    )

    config.check_dependencies(_Deps())

    assert config.getenum_safe(SYNTH, "deskull_engine") == DeskullEngine.BET
    assert config.getenum_safe(SYNTH, "segmentation_engine") == SegmentationEngine.FSL
    assert config.getenum_safe(SYNTH, "fmri_engine") == FmriEngine.FSL
    # The reset is persisted.
    reloaded = ConfigManager(global_base_folder=str(tmp_path))
    assert reloaded.getenum_safe(SYNTH, "deskull_engine") == DeskullEngine.BET


def test_engines_within_ram_are_kept(tmp_path):
    config = _global(
        tmp_path,
        8,
        deskull_engine=DeskullEngine.ANTSPYNET.name,
        segmentation_engine=SegmentationEngine.ANTS.name,
        fmri_engine=FmriEngine.NILEARN.name,
    )

    config.check_dependencies(_Deps())

    assert config.getenum_safe(SYNTH, "deskull_engine") == DeskullEngine.ANTSPYNET
    assert config.getenum_safe(SYNTH, "segmentation_engine") == SegmentationEngine.ANTS
    assert config.getenum_safe(SYNTH, "fmri_engine") == FmriEngine.NILEARN


def test_engine_is_kept_when_no_option_fits(tmp_path):
    # Without FSL and below 5 GB no brain extraction engine is usable: the
    # selection is left unchanged (the plugin then reports the shortage).
    config = _global(tmp_path, 4, deskull_engine=DeskullEngine.ANTSPYNET.name)

    config.check_dependencies(_Deps(fsl=False))

    assert config.getenum_safe(SYNTH, "deskull_engine") == DeskullEngine.ANTSPYNET


def test_synth_reconall_is_turned_off_below_its_ram(tmp_path):
    config = _global(tmp_path, 10, reconall="true")

    config.check_dependencies(_Deps())

    assert config.getboolean_safe(SYNTH, "reconall") is False


def test_synth_reconall_is_kept_with_enough_ram(tmp_path):
    config = _global(tmp_path, 24, reconall="true")

    config.check_dependencies(_Deps())

    assert config.getboolean_safe(SYNTH, "reconall") is True


def _subject(tmp_path, global_config) -> ConfigManager:
    folder = tmp_path / "subject"
    folder.mkdir()
    config = ConfigManager(str(folder), global_config=global_config)
    config[DataInputList.T13D]["freesurfer_step"] = FreesurferStep.SYNTHSEG.name
    return config


def test_subject_synthseg_checked_against_global_ram(tmp_path):
    # SynthSeg needs 14 GB of the global ram_gb.
    global_config = _global(tmp_path, 8)
    subject = _subject(tmp_path, global_config)

    subject.check_dependencies(_Deps(), global_config)

    assert (
        subject.getenum_safe(DataInputList.T13D, "freesurfer_step")
        != FreesurferStep.SYNTHSEG
    )


def test_subject_requirements_on_global_skipped_without_global(tmp_path):
    global_config = _global(tmp_path, 8)
    subject = _subject(tmp_path, global_config)

    subject.check_dependencies(_Deps())

    assert (
        subject.getenum_safe(DataInputList.T13D, "freesurfer_step")
        == FreesurferStep.SYNTHSEG
    )
