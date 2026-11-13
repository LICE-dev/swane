import pytest
import types

import swane.utils.ResourceManager as rm
from swane.config.config_enums import SegmentationEngine
from swane.utils.ResourceManager import ResourceManager


def test_to_gb_and_ram_calculations(monkeypatch):
    # fake virtual_memory total 8 GB
    class FakeVM:
        total = 8 * 1024**3

    monkeypatch.setattr(rm, "virtual_memory", lambda: FakeVM)
    # fake cpu_count and gpu_count
    monkeypatch.setattr(rm, "cpu_count", lambda: 8)
    # is_cuda() imports gpu_count lazily, so patch it at its source
    monkeypatch.setattr("nipype.utils.gpu_count.gpu_count", lambda: 0)

    assert rm.ResourceManager.to_gb(1024**3) == 1.0
    assert rm.ResourceManager.total_memory_gb() == 8.0
    # min and max ram are percentages of the total
    assert rm.ResourceManager.get_minimum_ram() <= rm.ResourceManager.total_memory_gb()
    assert rm.ResourceManager.get_maximum_ram() <= rm.ResourceManager.total_memory_gb()
    assert isinstance(rm.ResourceManager.get_default_cpu(), int)
    assert rm.ResourceManager.is_cuda() is False


def test_synth_requirements_and_cpu(monkeypatch):
    # monkeypatch get_os_type to a known key
    monkeypatch.setattr(
        "swane.utils.ResourceManager.get_os_type", lambda: "linux", raising=False
    )
    # But ResourceManager imports get_os_type via swane.utils.platform_and_tools_utils.get_os_type
    import swane.utils.platform_and_tools_utils as pu

    monkeypatch.setattr(pu, "get_os_type", lambda: "linux")

    # Ensure synth calls return numeric values
    assert isinstance(rm.ResourceManager.synth_strip_ram_requirements(), int)
    assert isinstance(rm.ResourceManager.synth_morph_ram_requirements(), int)
    assert isinstance(rm.ResourceManager.synth_seg_ram_requirements(), int)
    assert isinstance(rm.ResourceManager.synth_reconall_ram_requirements(), int)


def test_segmentation_engine_has_exactly_ants_and_fsl():
    assert {e.name for e in SegmentationEngine} == {"ANTS", "FSL"}
    # ANTS is declared first so it is the natural default/order
    assert list(SegmentationEngine)[0] is SegmentationEngine.ANTS


def test_atropos_ram_requirement_is_positive_number():
    assert isinstance(ResourceManager.atropos_ram_requirements(), (int, float))
    assert ResourceManager.atropos_ram_requirements() > 0


def test_nilearn_fmri_ram_requirement_is_positive_number():
    assert isinstance(ResourceManager.nilearn_fmri_ram_requirements(), (int, float))
    assert ResourceManager.nilearn_fmri_ram_requirements() > 0


def test_every_ram_requirement_has_a_windows_value():
    for name in dir(ResourceManager):
        if name.endswith("_RAM_REQUIREMENT"):
            table = getattr(ResourceManager, name)
            assert table["windows"] == table["other"], name


def _fake_total_ram(monkeypatch, total_gb):
    class FakeVM:
        total = total_gb * 1024**3

    monkeypatch.setattr(rm, "virtual_memory", lambda: FakeVM)


def test_subject_ram_limits(monkeypatch):
    _fake_total_ram(monkeypatch, 16)
    assert ResourceManager.get_maximum_ram() == pytest.approx(
        16 * ResourceManager.MAXIMUM_RAM_PERC / 100
    )
    # The floor is the same whatever the subject tab limit: the limits apply
    # to each tab and are never split among the tabs
    assert ResourceManager.get_minimum_subject_ram() == (
        ResourceManager.MINIMUM_SUBJECT_RAM
    )


@pytest.mark.parametrize(
    "total_gb, expected_min, expected_max",
    [
        (64, 5, 57.6),
        (8, 5, 7.2),
        # 90% of the RAM is below the floor: the maximum is raised to it
        (5.2, 5, 5),
        # Less RAM than the floor: both limits are the whole RAM
        (4, 4, 4),
    ],
)
def test_subject_ram_range_is_never_inverted(
    monkeypatch, total_gb, expected_min, expected_max
):
    _fake_total_ram(monkeypatch, total_gb)
    low = ResourceManager.get_minimum_subject_ram()
    high = ResourceManager.get_maximum_ram()
    assert low == pytest.approx(expected_min, abs=0.01)
    assert high == pytest.approx(expected_max, abs=0.01)
    assert low <= high <= ResourceManager.total_memory_gb()


@pytest.mark.parametrize("total_gb, expected", [(16, 11.2), (6, 5), (4, 4)])
def test_default_ram_is_within_the_subject_range(monkeypatch, total_gb, expected):
    # The ram_gb default (DEFAULT_RAM_PERC of the RAM) never goes below the
    # floor of a subject tab
    _fake_total_ram(monkeypatch, total_gb)
    assert ResourceManager.get_default_ram() == pytest.approx(expected, abs=0.01)
