# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
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


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AffineToRASInputSpec(BaseInterfaceInputSpec):
    in_transform = traits.Either(
        File(exists=True),
        traits.List(File(exists=True)),
        mandatory=True,
        desc="diff->ref registration transform to convert (ITK affine for ANTs, "
        "LTA for FreeSurfer); a list is treated as an affine-only ordered list",
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
        "diff2ref_ras.txt",
        usedefault=True,
        desc="output filename for the 4x4 diffusion-RAS -> reference-RAS affine",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AffineToRASOutputSpec(TraitedSpec):
    out_ras = File(exists=True, desc="4x4 diffusion-RAS -> reference-RAS affine (text)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AffineToRAS(BaseInterface):
    """Convert a linear diff->ref transform to a 4x4 RAS affine text file.

    :func:`dipy.tracking.streamline.transform_streamlines` moves streamlines
    between world spaces in RASMM, so it needs the plain diffusion-RAS ->
    reference-RAS affine, not an FSL ``.mat`` (voxel/scaled-mm) nor the ITK/LPS
    transform ANTs emits. nitransforms represents a loaded affine internally in
    RAS; for a diff->ref registration built with ``moving=diffusion`` and
    ``reference=T1``, its ``matrix`` maps reference-RAS -> moving-RAS (the
    resampling direction), so the diffusion-RAS -> reference-RAS affine the
    tracker consumes is its inverse. This node performs that conversion without
    depending on FSL or FreeSurfer command-line tools, mirroring
    :class:`~swane.nipype_pipeline.nodes.AffineToFSL.AffineToFSL`.
    """

    input_spec = AffineToRASInputSpec
    output_spec = AffineToRASOutputSpec

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
        # xfm.matrix is RAS->RAS mapping reference -> moving (ref->diff); the
        # tracker needs diff->ref, i.e. its inverse.
        diff2ref = np.linalg.inv(np.asarray(xfm.matrix, dtype=float))

        out_path = os.path.abspath(self.inputs.out_file)
        np.savetxt(out_path, diff2ref, fmt="%.10f")
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_ras"] = os.path.abspath(self.inputs.out_file)
        return outputs
