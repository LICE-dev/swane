# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nibabel import load, save

from os.path import abspath
import os
import shutil

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class CropFovInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    max_dim = traits.Int(mandatory=True)
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class CropFovOutputSpec(TraitedSpec):
    out_file = File(desc="the output image")


def _crop_window(profile, keep):
    """First index of the ``keep``-voxel window along one axis.

    The window is centred on the intensity centre of mass of ``profile`` (the
    image summed over the other axes), so a head off-centre in a wide field of
    view stays whole, and is clamped to the image bounds.
    """
    size = profile.shape[0]
    weights = np.clip(profile, 0, None)
    total = weights.sum()
    if total > 0:
        centre = float(np.dot(np.arange(size), weights) / total)
    else:
        centre = (size - 1) / 2.0
    start = int(round(centre - (keep - 1) / 2.0))
    return min(max(start, 0), size - keep)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class CropFov(BaseInterface):
    """
    If the FOV exceeds max_dim mm on any axis, crop that axis to max_dim mm.

    recon-all stops on a field of view larger than 256 mm. Each oversized axis
    keeps floor(max_dim / voxel size) voxels around the head's intensity
    centre of mass; the result is a plain voxel subset of the input, with the
    same grid orientation, voxel values and header, no resampling.

    """

    input_spec = CropFovInputSpec
    output_spec = CropFovOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()

        img = load(self.inputs.in_file)
        shape = img.header.get_data_shape()[:3]
        zooms = img.header.get_zooms()[:3]
        fov = [dim * vox for dim, vox in zip(shape, zooms)]

        if max(fov) <= self.inputs.max_dim:
            shutil.copyfile(self.inputs.in_file, out_file)
        else:
            data = img.get_fdata(dtype=np.float32)
            slicers = []
            for axis, (dim, vox) in enumerate(zip(shape, zooms)):
                if fov[axis] <= self.inputs.max_dim:
                    slicers.append(slice(None))
                    continue
                # the tolerance keeps an exact multiple (e.g. 256 / 0.8) whole
                keep = int(np.floor(self.inputs.max_dim / vox + 1e-6))
                other_axes = tuple(a for a in range(data.ndim) if a != axis)
                start = _crop_window(data.sum(axis=other_axes), keep)
                slicers.append(slice(start, start + keep))

            cropped = img.slicer[tuple(slicers)]
            # the slicer rebuilds the header from the shifted affine and drops
            # the original qform/sform codes; restore them
            for kind in ("qform", "sform"):
                code = int(img.header["%s_code" % kind])
                getattr(cropped, "set_%s" % kind)(cropped.affine, code=code)
            save(cropped, out_file)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "cropped_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        return outputs
