"""Unit tests for :class:`swane.nipype_pipeline.nodes.VenousCheck.VenousCheck`.

Only the deterministic ``FIRST``/``SECOND`` detection modes are exercised:
they pick the venous/anatomic volume by position and copy the files, with no
FSL ``ImageStats`` call (which the ``SD``/``MEAN`` modes would need).
"""

import os

from swane.config.config_enums import VeinDetectionMode
from swane.nipype_pipeline.nodes.VenousCheck import VenousCheck


class TestVenousCheckDeterministicModes:
    def test_first_mode_picks_first_as_veins(self, workspace, make_file):
        """``FIRST`` maps volume 0 -> veins and volume 1 -> anatomic."""
        first = make_file("v0.nii.gz", "VEINS")
        second = make_file("v1.nii.gz", "ANAT")
        node = VenousCheck()
        node.inputs.in_files = [first, second]
        node.inputs.detection_mode = VeinDetectionMode.FIRST

        result = node.run()

        with open(result.outputs.out_file_veins) as handle:
            assert handle.read() == "VEINS"
        with open(result.outputs.out_file_anat) as handle:
            assert handle.read() == "ANAT"

    def test_second_mode_picks_second_as_veins(self, workspace, make_file):
        """``SECOND`` maps volume 1 -> veins and volume 0 -> anatomic."""
        first = make_file("v0.nii.gz", "ANAT")
        second = make_file("v1.nii.gz", "VEINS")
        node = VenousCheck()
        node.inputs.in_files = [first, second]
        node.inputs.detection_mode = VeinDetectionMode.SECOND

        result = node.run()

        with open(result.outputs.out_file_veins) as handle:
            assert handle.read() == "VEINS"
        with open(result.outputs.out_file_anat) as handle:
            assert handle.read() == "ANAT"

    def test_output_filenames(self, workspace, make_file):
        """Outputs are pass-throughs: they keep the selected inputs' basenames."""
        node = VenousCheck()
        node.inputs.in_files = [
            make_file("v0.nii.gz", "a"),
            make_file("v1.nii.gz", "b"),
        ]
        node.inputs.detection_mode = VeinDetectionMode.FIRST
        result = node.run()

        # FIRST -> veins is in_files[0], anat is in_files[1]; no copy/rename.
        assert os.path.basename(result.outputs.out_file_veins) == "v0.nii.gz"
        assert os.path.basename(result.outputs.out_file_anat) == "v1.nii.gz"

    def test_default_detection_mode_is_standard_deviation(self):
        """The ``detection_mode`` enum trait defaults to the first member, ``SD``."""
        assert VenousCheck().inputs.detection_mode == VeinDetectionMode.SD
