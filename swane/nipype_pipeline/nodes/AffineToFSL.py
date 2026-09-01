import os

import numpy as np
import nibabel as nib
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
)


class AffineToFSLInputSpec(BaseInterfaceInputSpec):
    in_transform = traits.Either(
        File(exists=True),
        traits.List(File(exists=True)),
        mandatory=True,
        desc="diff->ref affine to convert (ITK .mat for ANTs, LTA for FreeSurfer)",
    )
    in_fmt = traits.Enum(
        "itk", "fs", usedefault=True, desc="source transform format for nitransforms"
    )
    source_file = File(
        exists=True, mandatory=True, desc="registration moving image (b0/nodif brain)"
    )
    reference_file = File(
        exists=True, mandatory=True, desc="registration fixed image (reference brain)"
    )
    out_file = traits.Str(
        "diff2ref.mat", usedefault=True, desc="forward FSL matrix filename (diff->ref)"
    )
    out_file_inverse = traits.Str(
        "ref2diff.mat", usedefault=True, desc="inverse FSL matrix filename (ref->diff)"
    )


class AffineToFSLOutputSpec(TraitedSpec):
    out_fsl = File(exists=True, desc="diff->ref affine in FSL format")
    out_fsl_inverse = File(exists=True, desc="ref->diff affine in FSL format")


class AffineToFSL(BaseInterface):
    """Convert a linear diff<->ref transform to an FSL .mat pair via nitransforms.

    probtrackx accepts only a single FSL transform per slot; ANTs (and, in
    future, SynthMorph outside FreeSurfer) produce ITK/LTA affines. This node
    bridges them without depending on FSL or FreeSurfer command-line tools.
    """

    input_spec = AffineToFSLInputSpec
    output_spec = AffineToFSLOutputSpec

    def _run_interface(self, runtime):
        from nitransforms import linear

        transform = self.inputs.in_transform
        if isinstance(transform, (list, tuple)):
            # diff<->ref is affine-only: the ordered list holds a single affine
            transform = transform[-1]

        ref_img = nib.load(self.inputs.reference_file)
        mov_img = nib.load(self.inputs.source_file)

        xfm = linear.load(
            transform, fmt=self.inputs.in_fmt, reference=ref_img, moving=mov_img
        )
        xfm.reference = ref_img

        fwd_path = os.path.abspath(self.inputs.out_file)
        xfm.to_filename(fwd_path, fmt="fsl", moving=mov_img)

        matrix = np.loadtxt(fwd_path)
        inv_path = os.path.abspath(self.inputs.out_file_inverse)
        np.savetxt(inv_path, np.linalg.inv(matrix), fmt="%.10f")
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_fsl"] = os.path.abspath(self.inputs.out_file)
        outputs["out_fsl_inverse"] = os.path.abspath(self.inputs.out_file_inverse)
        return outputs
