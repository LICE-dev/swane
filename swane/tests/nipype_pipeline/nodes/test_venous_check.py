"""Unit tests for :class:`swane.nipype_pipeline.nodes.VenousCheck.VenousCheck`.

The deterministic ``FIRST``/``SECOND`` modes pick the venous/anatomic volume by
position. The automatic modes (``KURTOSIS``, ``SD``, ``MEAN``) load the two
volumes with nibabel and pick the venous phase from an intensity statistic; they
are exercised here with synthetic volumes that mimic a phase-contrast pair.
"""

import os

import nibabel as nib
import numpy as np

from swane.config.config_enums import VeinDetectionMode
from swane.nipype_pipeline.nodes.VenousCheck import VenousCheck


def _broad_anatomic(shape=(20, 20, 20), seed=0):
    """Anatomic magnitude phase: a broad tissue distribution (low kurtosis)."""
    rng = np.random.default_rng(seed)
    return np.abs(rng.normal(100.0, 25.0, shape)).astype(np.float32)


def _sparse_venous(shape=(20, 20, 20), seed=1, n_bright=40):
    """Venous angiographic phase: a suppressed background with a few very bright
    vessel voxels, i.e. a sparse, heavy-tailed (high kurtosis) distribution."""
    rng = np.random.default_rng(seed)
    data = np.abs(rng.normal(8.0, 3.0, shape)).astype(np.float32)
    idx = rng.choice(data.size, size=n_bright, replace=False)
    data.flat[idx] = rng.uniform(400.0, 900.0, size=n_bright).astype(np.float32)
    return data


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

    def test_default_detection_mode_is_kurtosis(self):
        """The ``detection_mode`` enum trait defaults to the first member,
        ``KURTOSIS`` (also the persisted preference default)."""
        assert VenousCheck().inputs.detection_mode == VeinDetectionMode.KURTOSIS


class TestVenousCheckStatisticalModes:
    """Automatic modes select the venous phase from an intensity statistic."""

    def _run(self, make_nifti, mode, anat_data, veins_data, order):
        """Save an anat/veins pair in ``order`` and return (veins, anat) data."""
        files = {}
        files["anat"] = make_nifti(name="anat.nii.gz", data=anat_data)
        files["veins"] = make_nifti(name="veins.nii.gz", data=veins_data)
        node = VenousCheck()
        node.inputs.in_files = [files[order[0]], files[order[1]]]
        node.inputs.detection_mode = mode
        result = node.run()
        return (
            np.asarray(nib.load(result.outputs.out_file_veins).dataobj),
            np.asarray(nib.load(result.outputs.out_file_anat).dataobj),
        )

    def test_kurtosis_picks_sparse_heavy_tailed_volume(self, workspace, make_nifti):
        """KURTOSIS: the sparse, heavy-tailed volume is the venous phase,
        regardless of its position in the input list."""
        anat = _broad_anatomic()
        veins = _sparse_venous()
        for order in (("veins", "anat"), ("anat", "veins")):
            got_veins, got_anat = self._run(
                make_nifti, VeinDetectionMode.KURTOSIS, anat, veins, order
            )
            assert np.array_equal(got_veins, veins)
            assert np.array_equal(got_anat, anat)

    def test_kurtosis_succeeds_where_sd_is_misled(self, workspace, make_nifti):
        """On a realistic sparse venous phase the bright vessels inflate the
        standard deviation above the anatomic one, so SD selects the wrong
        volume while KURTOSIS still selects the venous phase."""
        anat = _broad_anatomic()
        veins = _sparse_venous()
        # SD picks the lower-std volume as venous -> here it is fooled (anat).
        sd_veins, _ = self._run(
            make_nifti, VeinDetectionMode.SD, anat, veins, ("veins", "anat")
        )
        assert np.array_equal(sd_veins, anat)
        # KURTOSIS is not fooled on the same pair.
        kurt_veins, _ = self._run(
            make_nifti, VeinDetectionMode.KURTOSIS, anat, veins, ("veins", "anat")
        )
        assert np.array_equal(kurt_veins, veins)

    def test_sd_and_mean_pick_the_darker_volume(self, workspace, make_nifti):
        """SD/MEAN keep the legacy behaviour: the darker (lower statistic)
        volume is the venous one."""
        rng = np.random.default_rng(2)
        anat = np.abs(rng.normal(100.0, 25.0, (20, 20, 20))).astype(np.float32)
        # A darker, narrower venous phase without bright outliers: lower mean
        # AND lower std than the anatomic volume.
        veins = np.abs(rng.normal(30.0, 5.0, (20, 20, 20))).astype(np.float32)
        for mode in (VeinDetectionMode.SD, VeinDetectionMode.MEAN):
            got_veins, got_anat = self._run(
                make_nifti, mode, anat, veins, ("anat", "veins")
            )
            assert np.array_equal(got_veins, veins)
            assert np.array_equal(got_anat, anat)
