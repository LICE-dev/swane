# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import os
import shutil
from os.path import abspath
import numpy as np
import nibabel as nib
from nibabel.orientations import io_orientation, axcodes2ornt, ornt_transform
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

from swane.nipype_pipeline.interfaces.geometry.bvec_frame import fsl_bvec_frame


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ForceOrientInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    out_file = File(desc="the output image")
    in_bvec = File(
        exists=True,
        desc="FSL-convention b-vectors of in_file, re-expressed on the output grid",
    )
    out_bvec = File(desc="the output b-vectors")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ForceOrientOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")
    out_bvec = File(desc="the b-vectors on the output grid (only with in_bvec)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ForceOrient(BaseInterface):
    """
    Converts an image in radiological convention and in RL PA IS orientation.

    FSL-convention b-vectors are expressed along the voxel axes, so when
    ``in_bvec`` is given they follow the same axis permutation/flip as the
    voxels and keep pointing along the same physical gradients.

    """

    input_spec = ForceOrientInputSpec
    output_spec = ForceOrientOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        in_nii = nib.load(self.inputs.in_file)
        # radiological convention with RL PA IS axes is the LAS orientation.
        # Voxel data is only permuted/flipped, so dtype and scaling are
        # preserved as they are and the anatomy keeps its world coordinates
        transform = ornt_transform(
            io_orientation(in_nii.affine), axcodes2ornt(("L", "A", "S"))
        )
        out_nii = in_nii.as_reoriented(transform)
        nib.save(out_nii, out_file)

        if isdefined(self.inputs.in_bvec):
            self._reorient_bvec(in_nii.affine, out_nii.affine)

        return runtime

    def _reorient_bvec(self, in_affine, out_affine):
        """Re-express the b-vectors on the reoriented grid.

        A b-vector b on the input grid points along W_in b in world, W the
        FSL frame of each grid; on the output grid the same gradient is
        W_out^T W_in b. The reorientation only permutes/flips axes, so that
        matrix is a signed permutation: it is snapped to one, the values are
        moved and negated but never interpolated, and an image already LAS
        keeps its b-vector file byte for byte.
        """
        out_bvec = self._gen_outbvecname()
        change = fsl_bvec_frame(out_affine).T @ fsl_bvec_frame(in_affine)
        permutation = np.round(change)
        magnitude = np.abs(permutation)
        is_signed_permutation = (
            np.isin(magnitude, (0.0, 1.0)).all()
            and (magnitude.sum(axis=0) == 1).all()
            and (magnitude.sum(axis=1) == 1).all()
        )
        if not is_signed_permutation or not np.allclose(change, permutation, atol=1e-6):
            raise ValueError(
                "The reorientation is not an axis permutation/flip; "
                "the b-vectors cannot follow it"
            )

        if np.array_equal(permutation, np.eye(3)):
            if not (
                os.path.exists(out_bvec)
                and os.path.samefile(self.inputs.in_bvec, out_bvec)
            ):
                shutil.copyfile(self.inputs.in_bvec, out_bvec)
            return

        bvecs = np.loadtxt(self.inputs.in_bvec, ndmin=2)
        if bvecs.shape[0] != 3:
            raise ValueError(
                "Expected FSL b-vectors as 3 rows, got shape %s" % (bvecs.shape,)
            )
        # + 0.0 turns the -0.0 a negated zero component would print into 0.
        np.savetxt(out_bvec, permutation @ bvecs + 0.0, fmt="%.10g")

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _gen_outbvecname(self):
        out_bvec = self.inputs.out_bvec
        if not isdefined(out_bvec):
            out_bvec = os.path.basename(self.inputs.in_bvec)
        return abspath(out_bvec)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        if isdefined(self.inputs.in_bvec):
            outputs["out_bvec"] = self._gen_outbvecname()
        return outputs
