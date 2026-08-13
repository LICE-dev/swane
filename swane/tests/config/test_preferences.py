"""Integrity tests for the preference registry and config enums."""

from enum import Enum

import pytest

from swane.config.PreferenceEntry import PreferenceEntry
from swane.config.preference_list import GLOBAL_PREFERENCES, WF_PREFERENCES
from swane.config.config_enums import (
    InputTypes,
    ImageModality,
    FreesurferStep,
    Planes,
)


def _all_entries():
    for registry in (GLOBAL_PREFERENCES, WF_PREFERENCES):
        for category, entries in registry.items():
            assert isinstance(entries, dict)
            for key, entry in entries.items():
                yield category, key, entry


class TestPreferenceRegistry:

    def test_entries_are_well_formed(self):
        seen = 0
        for _category, key, entry in _all_entries():
            seen += 1
            assert isinstance(key, str) and key, "empty preference key"
            assert isinstance(entry, PreferenceEntry)
            assert isinstance(entry.input_type, InputTypes)
            assert isinstance(entry.label, str)
        assert seen > 0, "no preferences discovered"

    def test_enum_entries_declare_value_enum(self):
        for _category, key, entry in _all_entries():
            if entry.input_type == InputTypes.ENUM:
                assert entry.value_enum is not None, (
                    "ENUM preference %r without value_enum" % key
                )
                assert isinstance(entry.value_enum, type)
                assert issubclass(entry.value_enum, Enum)

    def test_numeric_ranges_are_pairs(self):
        for _category, key, entry in _all_entries():
            if entry.range is not None:
                assert isinstance(entry.range, list)
                assert len(entry.range) == 2, "range for %r is not a pair" % key
                assert entry.range[0] <= entry.range[1]


class TestConfigEnums:

    def test_image_modality_from_string(self):
        assert ImageModality.from_string("mr") == ImageModality.RM
        assert ImageModality.from_string("MR") == ImageModality.RM
        assert ImageModality.from_string("ct") == ImageModality.CT
        assert ImageModality.from_string("bogus") is None

    def test_freesurfer_step_helpers(self):
        assert FreesurferStep.RECONALL.has_surface() is True
        assert FreesurferStep.AUTORECON_PIAL.has_surface() is True
        assert FreesurferStep.SYNTHSEG.has_surface() is False
        assert FreesurferStep.DISABLED.has_surface() is False

        assert FreesurferStep.SYNTHSEG.has_parcellation() is True
        assert FreesurferStep.RECONALL.has_parcellation() is True
        assert FreesurferStep.DISABLED.has_parcellation() is False

    def test_planes(self):
        assert {p.name for p in Planes} == {"TRA", "COR", "SAG"}
