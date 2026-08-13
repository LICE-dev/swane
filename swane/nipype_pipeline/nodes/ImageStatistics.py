"""
Native image statistics for the swane workflows.

A single interface computes the few quantities the pipeline needs, with
explicit inputs and named outputs, using nibabel and numpy only.

Definitions used here:

* the *domain* is the whole image, or only the voxels of ``mask_file``
  (values greater than zero) when a mask is given
* ``mean``, ``std``, ``n_voxels`` and ``volume`` describe the **non zero**
  voxels of the domain, the usual convention for intensity statistics where
  the zero background carries no signal
* ``min_value``, ``max_value`` and the percentiles describe **all** the
  voxels of the domain
* ``std`` is the sample standard deviation (N-1 denominator)
* percentiles use the nearest-rank definition (numpy ``method="higher"``)
"""

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


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ImageStatisticsInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    mask_file = File(
        exists=True, desc="restrict the statistics to the voxels of this mask"
    )
    percentiles = traits.List(
        traits.Float,
        value=[],
        usedefault=True,
        desc="percentiles to compute, each between 0 and 100",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ImageStatisticsOutputSpec(TraitedSpec):
    mean = traits.Float(desc="mean of the non zero voxels")
    std = traits.Float(desc="sample standard deviation of the non zero voxels")
    n_voxels = traits.Int(desc="number of non zero voxels")
    volume = traits.Float(desc="volume of the non zero voxels in mm3")
    min_value = traits.Float(desc="minimum value")
    max_value = traits.Float(desc="maximum value")
    percentile_values = traits.List(
        traits.Float, desc="the requested percentiles, in the same order"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ImageStatistics(BaseInterface):
    """
    Calculates intensity statistics of an image, optionally inside a mask.

    """

    input_spec = ImageStatisticsInputSpec
    output_spec = ImageStatisticsOutputSpec

    def _run_interface(self, runtime):
        in_nii = nib.load(self.inputs.in_file)
        # float64 keeps the accumulation of large volumes accurate
        data = np.asarray(in_nii.get_fdata(), dtype=np.float64)
        voxel_volume = float(np.prod(in_nii.header.get_zooms()[:3]))

        if isdefined(self.inputs.mask_file):
            domain = data[nib.load(self.inputs.mask_file).get_fdata() > 0]
        else:
            domain = data.ravel()

        non_zero = domain[domain != 0]

        self.mean = float(non_zero.mean()) if non_zero.size else 0.0
        self.std = float(non_zero.std(ddof=1)) if non_zero.size > 1 else 0.0
        self.n_voxels = int(non_zero.size)
        self.volume = float(non_zero.size) * voxel_volume
        self.min_value = float(domain.min()) if domain.size else 0.0
        self.max_value = float(domain.max()) if domain.size else 0.0
        self.percentile_values = [
            float(np.percentile(domain, percentile, method="higher"))
            for percentile in self.inputs.percentiles
        ]

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["mean"] = self.mean
        outputs["std"] = self.std
        outputs["n_voxels"] = self.n_voxels
        outputs["volume"] = self.volume
        outputs["min_value"] = self.min_value
        outputs["max_value"] = self.max_value
        outputs["percentile_values"] = self.percentile_values
        return outputs
