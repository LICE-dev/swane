"""Resource limits MainWorkflow reads from the global configuration."""

from collections import defaultdict
from types import SimpleNamespace

import pytest

from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.MainWorkflow import MainWorkflow

PERF = GlobalPrefCategoryList.PERFORMANCE


@pytest.fixture
def resources_owner(tmp_path):
    """Stands in for a MainWorkflow: only what set_resources_configuration reads."""
    global_config = ConfigManager(global_base_folder=str(tmp_path))
    return SimpleNamespace(
        global_config=global_config, subject_config=defaultdict(dict)
    )


@pytest.mark.parametrize("max_subj_gpu, expected", [("-1", 2), ("1", 1), ("3", 3)])
def test_max_gpu(monkeypatch, resources_owner, max_subj_gpu, expected):
    # A negative max_subj_gpu (hand-edited configuration) means every visible GPU
    monkeypatch.setattr("nipype.utils.gpu_count.gpu_count", lambda: 2)
    resources_owner.global_config[PERF]["max_subj_gpu"] = max_subj_gpu

    MainWorkflow.set_resources_configuration(resources_owner)

    assert resources_owner.max_gpu == expected


@pytest.mark.parametrize(
    "max_subj_cpu, expected", [("32", 7), ("7", 7), ("2", 2), ("-1", 7)]
)
def test_max_cpu_is_within_the_computer_cores(
    monkeypatch, resources_owner, max_subj_cpu, expected
):
    # A configuration from a computer with more cores (copied ~/.SWANe, shared
    # home, resized VM) never asks for more threads than this computer has
    from swane.utils.ResourceManager import ResourceManager

    monkeypatch.setattr(ResourceManager, "get_max_cpu", staticmethod(lambda: 7))
    resources_owner.global_config[PERF]["max_subj_cpu"] = max_subj_cpu

    MainWorkflow.set_resources_configuration(resources_owner)

    assert resources_owner.max_cpu == expected
