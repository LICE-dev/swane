"""Unit tests for :class:`swane.nipype_pipeline.nodes.AsymmetryIndex.AsymmetryIndex`.

The node computes the asymmetry index ``(in - swapped) / (in + swapped)`` with
``nibabel``/``numpy`` only (no FSL), so both the output-name helper and the
actual arithmetic are exercised here on tiny synthetic volumes.
"""

import os

import numpy as np
import nibabel as nib
import pytest

from swane.nipype_pipeline.nodes.AsymmetryIndex import AsymmetryIndex


class TestAsymmetryIndexOutputName:
    def test_default_name_prefixes_input(self, make_file):
        """The default output name is ``Aindex_<input basename>``."""
        node = AsymmetryIndex()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        out = node._gen_outfilename()
        assert os.path.basename(out) == "Aindex_t1.nii.gz"
        assert os.path.isabs(out)

    def test_explicit_name_is_preserved(self, make_file):
        """An explicit ``out_file`` overrides the generated name."""
        node = AsymmetryIndex()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        node.inputs.out_file = "custom.nii.gz"
        assert os.path.basename(node._gen_outfilename()) == "custom.nii.gz"

    def test_list_outputs_matches_generated_name(self, make_file):
        """``_list_outputs`` exposes the same generated output path."""
        node = AsymmetryIndex()
        node.inputs.in_file = make_file("t1.nii.gz", "x")
        assert node._list_outputs()["out_file"] == node._gen_outfilename()


class TestAsymmetryIndexComputation:
    """The ``(in - swapped) / (in + swapped)`` map, with 0 on division by zero."""

    def test_asymmetry_index_values(self, workspace, make_nifti):
        in_data = np.array([3, 1, 0, 2, 0, 0, 0, 0], dtype=np.float32).reshape(2, 2, 2)
        swapped = np.array([1, 1, 0, 6, 0, 0, 0, 0], dtype=np.float32).reshape(2, 2, 2)
        node = AsymmetryIndex()
        node.inputs.in_file = make_nifti("t1.nii.gz", data=in_data)
        node.inputs.swapped_file = make_nifti("t1_swap.nii.gz", data=swapped)

        result = node.run()
        out = nib.load(result.outputs.out_file).get_fdata().ravel()

        # (3-1)/(3+1)=0.5 ; (1-1)/2=0 ; 0/0 -> 0 ; (2-6)/8=-0.5
        assert out[0] == pytest.approx(0.5)
        assert out[1] == pytest.approx(0.0)
        assert out[2] == pytest.approx(0.0)
        assert out[3] == pytest.approx(-0.5)
