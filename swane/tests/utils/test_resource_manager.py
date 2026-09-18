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
    monkeypatch.setattr(rm, "gpu_count", lambda: 0)

    assert rm.ResourceManager.to_gb(1024**3) == 1.0
    assert rm.ResourceManager.total_memory_gb() == 8.0
    # min ram is max(MINIMUM_RAM, perc of total)
    assert rm.ResourceManager.get_minimum_ram() <= rm.ResourceManager.total_memory_gb()
    assert rm.ResourceManager.get_maximum_ram() <= rm.ResourceManager.total_memory_gb()
    assert isinstance(rm.ResourceManager.get_default_cpu(), int)


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
