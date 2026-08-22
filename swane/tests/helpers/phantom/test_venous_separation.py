"""The phantom venous pair must let VenousCheck pick the angiographic phase.

The pre-release sweep wires the two venous shapes to two detection modes and
grades vein localization end to end, but that takes hours. This fast guard runs
the real :class:`VenousCheck` node on the phantom's *rendered* venous volumes and
asserts the phase selection the sweep relies on, so an accidental change to the
venous LUTs is caught in the light suite instead of only in a full sweep:

* the single 2-volume series (``venous_mr``) must be separable by KURTOSIS (the
  default, used on the single-series shape);
* the two-series pair (``venous_mr_split_*``) must be separable by SD (used on
  the two-series shape) -- and, since the phantom is deliberately realistic,
  KURTOSIS agrees there too.

Building the tissue model and rendering the volumes takes tens of seconds, so
this is a ``heavy`` test (opt in with ``--run-heavy``); it also needs the
``fsaverage`` subject, so it skips cleanly where FreeSurfer is not installed.
"""

import os
from dataclasses import replace

import nibabel as nib
import numpy as np
import pytest

from swane.config.config_enums import VeinDetectionMode
from swane.nipype_pipeline.nodes.VenousCheck import VenousCheck
from swane.tests.helpers.phantom import catalog as phantom_catalog
from swane.tests.helpers.phantom.dataset import PhantomProfile
from swane.tests.helpers.phantom.sequences import render_structural


def _has_fsaverage() -> bool:
    home = os.environ.get("FREESURFER_HOME")
    if not home:
        return False
    return os.path.isdir(os.path.join(home, "subjects", "fsaverage", "mri"))


pytestmark = [
    pytest.mark.heavy,
    pytest.mark.skipif(
        not _has_fsaverage(),
        reason="needs $FREESURFER_HOME/subjects/fsaverage to build the phantom",
    ),
]


@pytest.fixture(scope="module")
def tissue():
    from swane.tests.helpers.phantom.tissue import build_tissue_model

    return build_tissue_model(deform=True)


@pytest.fixture(scope="module")
def venous_entries():
    entries = phantom_catalog.build_catalog(PhantomProfile())
    return {e.input_name: e for e in entries}


def _save(tmp_path, name, data, affine):
    path = str(tmp_path / name)
    nib.save(nib.Nifti1Image(np.asarray(data, dtype=np.float32), affine), path)
    return path


def _pick_veins(in_files, mode):
    """Run the real VenousCheck node and return its chosen venous file."""
    node = VenousCheck()
    node.inputs.in_files = in_files
    node.inputs.detection_mode = mode
    return node.run().outputs.out_file_veins


def test_single_series_separated_by_kurtosis(tmp_path, tissue, venous_entries):
    """venous_mr: anatomic phase + velocity phase, KURTOSIS picks the velocity."""
    entry = venous_entries["venous_mr"]
    anat, affine = render_structural(
        tissue, entry.spec, seed=entry.series_number, pose=entry.pose
    )
    velocity_spec = replace(entry.spec, lut=entry.extra["second_lut"])
    velocity, _ = render_structural(
        tissue, velocity_spec, seed=entry.series_number + 100, pose=entry.pose
    )

    anat_file = _save(tmp_path, "vol0000.nii.gz", anat, affine)
    velocity_file = _save(tmp_path, "vol0001.nii.gz", velocity, affine)

    chosen = _pick_veins([anat_file, velocity_file], VeinDetectionMode.KURTOSIS)
    assert chosen == velocity_file


def test_two_series_separated_by_sd(tmp_path, tissue, venous_entries):
    """venous_mr_split_*: SD (the two-series mode) picks the angiographic phase,
    and the realistic phantom lets KURTOSIS reach the same answer."""
    anat_entry = venous_entries["venous_mr_split_anat"]
    angio_entry = venous_entries["venous_mr_split_angio"]
    anat, affine = render_structural(
        tissue, anat_entry.spec, seed=anat_entry.series_number, pose=anat_entry.pose
    )
    angio, _ = render_structural(
        tissue, angio_entry.spec, seed=angio_entry.series_number, pose=angio_entry.pose
    )

    # The workflow merges VENOUS_MR then VENOUS_MR2, i.e. anatomic then angio.
    anat_file = _save(tmp_path, "anat.nii.gz", anat, affine)
    angio_file = _save(tmp_path, "angio.nii.gz", angio, affine)

    for mode in (VeinDetectionMode.SD, VeinDetectionMode.KURTOSIS):
        chosen = _pick_veins([anat_file, angio_file], mode)
        assert chosen == angio_file, "%s misidentified the venous phase" % mode
