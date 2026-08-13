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
