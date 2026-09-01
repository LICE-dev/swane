"""Unit tests for :mod:`swane.utils.ToolReference`."""

from swane.utils.ToolReference import (
    get_command_info,
    tool_reference_list,
    ToolReference,
    Package,
)


def test_get_command_info_known_key():
    ref = get_command_info("BET")
    assert isinstance(ref, ToolReference)
    assert ref.command == "bet"
    assert ref.package == Package.FSL


def test_get_command_info_equivalent_key():
    # ApplyXFM is registered as an alias of FLIRT
    assert get_command_info("ApplyXFM") is get_command_info("FLIRT")


def test_get_command_info_unknown_key():
    assert get_command_info("DoesNotExist") is None


def test_utility_urls_get_command_anchor():
    # urls ending in '#' are completed with the command name at import time
    merge = tool_reference_list["MERGE"]
    assert merge.url.endswith(merge.command)


def test_ants_tools_share_a_single_package_label():
    # antspyx and antspynet tools are grouped under one "ANTs" tab, not
    # scattered across OTHER.
    for key in (
        "AntsN4BiasFieldCorrection",
        "AntsRegistration",
        "AntsPyNetBrainExtraction",
    ):
        assert get_command_info(key).package == Package.ANTS


def test_get_command_info_matches_actual_interface_class_names():
    # keys must match nipype interface.__class__.__name__, since that is what
    # NipypeNodeRuntimeWidget looks up (see AntsN4BiasFieldCorrection in
    # swane.nipype_pipeline.nodes.AntsN4BiasFieldCorrection).
    assert get_command_info("AntsN4BiasFieldCorrection") is not None


def test_antspynet_brain_extraction_is_registered():
    ref = get_command_info("AntsPyNetBrainExtraction")
    assert isinstance(ref, ToolReference)
    assert ref.package == Package.ANTS
    assert ref.references
