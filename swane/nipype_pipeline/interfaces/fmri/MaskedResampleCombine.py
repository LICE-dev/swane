# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os

import nibabel as nib
import numpy as np
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)


def masked_resample_combine(z, pos_mask, neg_mask, mask_thr=0.5):
    """Keep the resampled z where a resampled survivor mask of the same sign
    exceeds `mask_thr`, zero elsewhere.

    ``z`` is the unthresholded map and ``pos_mask``/``neg_mask`` the positive
    and negative survivor masks of the decision taken on the original grid,
    all three already resampled onto the output grid with linear
    interpolation. The output is z where (pos_mask > mask_thr and z > 0) or
    (neg_mask > mask_thr and z < 0): the survivors keep their continuous
    values and no sub-threshold ramp is created at the cluster borders.
    """
    keep = ((pos_mask > mask_thr) & (z > 0)) | ((neg_mask > mask_thr) & (z < 0))
    return np.where(keep, z, 0.0).astype(np.float32)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class MaskedResampleCombineInputSpec(BaseInterfaceInputSpec):
    z_file = File(
        exists=True,
        mandatory=True,
        desc="Unthresholded 3D z map, resampled onto the output grid",
    )
    pos_mask_file = File(
        exists=True,
        mandatory=True,
        desc="Positive survivor mask, resampled onto the output grid (linear)",
    )
    neg_mask_file = File(
        exists=True,
        mandatory=True,
        desc="Negative survivor mask, resampled onto the output grid (linear)",
    )
    mask_thr = traits.Float(
        0.5,
        usedefault=True,
        desc="Threshold that re-binarises the resampled survivor masks",
    )
    out_file = File(
        desc="Output file name (default: 'masked_' + the z_file name)",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class MaskedResampleCombineOutputSpec(TraitedSpec):
    out_file = File(desc="Thresholded z map on the output grid (float32)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class MaskedResampleCombine(BaseInterface):
    """
    Combine a resampled unthresholded z map with the resampled survivor
    masks of a threshold decided on the original grid (see
    `masked_resample_combine`).

    The threshold is decided where the map was estimated; only the values
    and the survivor masks are moved to the output space, each with linear
    interpolation, and the masks are re-binarised at `mask_thr` (0.5 is the
    usual partial-volume threshold for a linearly interpolated mask,
    Zwanenburg et al. 2020). Keeping the resampled z only where the mask of
    the same sign survives is a design choice of this interface, with no
    published source.

    References:
    - Zwanenburg A, et al. (2020). The Image Biomarker Standardization
      Initiative: standardized quantitative radiomics for high-throughput
      image-based phenotyping. Radiology 295(2):328-338.
      doi:10.1148/radiol.2020191145 (reference manual: partial-volume
      threshold of interpolated masks)
    """

    input_spec = MaskedResampleCombineInputSpec
    output_spec = MaskedResampleCombineOutputSpec

    def _out_path(self):
        if isdefined(self.inputs.out_file):
            name = os.path.basename(self.inputs.out_file)
        else:
            name = "masked_" + os.path.basename(self.inputs.z_file)
        return os.path.abspath(name)

    def _run_interface(self, runtime):
        z_img = nib.load(self.inputs.z_file)
        z = z_img.get_fdata()
        pos = nib.load(self.inputs.pos_mask_file).get_fdata()
        neg = nib.load(self.inputs.neg_mask_file).get_fdata()
        if pos.shape != z.shape or neg.shape != z.shape:
            raise ValueError(
                "MaskedResampleCombine: z %s, positive mask %s and negative "
                "mask %s are not on the same grid" % (z.shape, pos.shape, neg.shape)
            )

        out = masked_resample_combine(z, pos, neg, self.inputs.mask_thr)
        header = z_img.header.copy()
        header.set_data_dtype(np.float32)
        nib.save(nib.Nifti1Image(out, z_img.affine, header), self._out_path())
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_file"] = self._out_path()
        return outputs
