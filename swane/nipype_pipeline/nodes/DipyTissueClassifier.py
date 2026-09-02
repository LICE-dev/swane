# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Tissue classification of a T1-weighted structural image.

Runs dipy's Hidden Markov Random Field classifier
(``dipy.segment.tissue.TissueClassifierHMRF``) to derive partial volume
estimate (PVE) maps for CSF, gray matter and white matter, feeding the CMC
stopping criterion and PFT reinitialisation in ``DipyTracking``.

``TissueClassifierHMRF.classify`` sorts its tissue classes by ascending mean
intensity and drops the extra background class from the returned PVE array
(confirmed against the installed dipy 1.12.0 source and empirically on a
synthetic three-block phantom). On a T1 image this puts CSF (darkest) in
channel 0, gray matter in channel 1 and white matter (brightest) in channel 2.
"""

import os
from os.path import abspath

import nibabel as nib
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

OMP_THREADS_VAR = "OMP_NUM_THREADS"

# dipy tutorial defaults for dipy.segment.tissue.TissueClassifierHMRF.classify:
# 3 tissue classes (CSF/GM/WM) and a moderate Markov smoothing weight.
HMRF_NCLASSES = 3
HMRF_BETA = 0.1

_PVE_FIELDS = ("pve_csf", "pve_gm", "pve_wm")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyTissueClassifierInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        desc="the input T1-weighted brain-extracted reference image",
    )
    out_prefix = traits.Str(desc="prefix for the output PVE map filenames")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyTissueClassifierOutputSpec(TraitedSpec):
    pve_csf = File(desc="the CSF partial volume estimate map")
    pve_gm = File(desc="the gray matter partial volume estimate map")
    pve_wm = File(desc="the white matter partial volume estimate map")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyTissueClassifier(BaseInterface):
    """
    Segments a T1-weighted brain image into CSF, gray matter and white
    matter partial volume estimate maps using dipy's HMRF classifier.

    """

    input_spec = DipyTissueClassifierInputSpec
    output_spec = DipyTissueClassifierOutputSpec

    def _run_interface(self, runtime):
        from dipy.segment import tissue

        in_nii = nib.load(self.inputs.in_file)
        data = in_nii.get_fdata()

        previous_omp = os.environ.get(OMP_THREADS_VAR)
        os.environ[OMP_THREADS_VAR] = "1"
        try:
            classifier = tissue.TissueClassifierHMRF()
            _, _, pve = classifier.classify(data, HMRF_NCLASSES, HMRF_BETA)
        finally:
            if previous_omp is None:
                os.environ.pop(OMP_THREADS_VAR, None)
            else:
                os.environ[OMP_THREADS_VAR] = previous_omp

        for index, field in enumerate(_PVE_FIELDS):
            nib.save(
                nib.Nifti1Image(pve[..., index], in_nii.affine, in_nii.header),
                self._gen_outfilename(field),
            )

        return runtime

    def _gen_outfilename(self, field):
        suffix = field[len("pve_") :]
        prefix = self.inputs.out_prefix
        if not isdefined(prefix):
            prefix = "tissue"
        return abspath(f"{prefix}_{suffix}.nii.gz")

    def _list_outputs(self):
        outputs = self.output_spec().get()
        for field in _PVE_FIELDS:
            outputs[field] = self._gen_outfilename(field)
        return outputs
