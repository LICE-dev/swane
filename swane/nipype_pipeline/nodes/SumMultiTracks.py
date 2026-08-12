# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
import os

import nibabel as nib
import numpy as np
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    InputMultiPath,
    File,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class SumMultiTracksInputSpec(BaseInterfaceInputSpec):
    path_files = InputMultiPath(
        File(exists=True), mandatory=True, desc="list of path file to sum togheter"
    )
    waytotal_files = InputMultiPath(
        File(exists=True), mandatory=True, desc="list of waytotal files to sum togheter"
    )
    out_file = File(desc="the output image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SumMultiTracksOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc="the output image")
    waytotal_sum = File(exists=True, desc="the output waytotal file")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class SumMultiTracks(BaseInterface):
    """
    Merges results from multiple tractography runs.

    """

    input_spec = SumMultiTracksInputSpec
    output_spec = SumMultiTracksOutputSpec

    def _run_interface(self, runtime):
        out_file = self._gen_outfilename()
        waytotal_sum_file = self._gen_waytotal_outfilename()

        # sum the tractography path maps (p0 + p1 + ... + pn, no doubling)
        first_nii = nib.load(self.inputs.path_files[0])
        acc = first_nii.get_fdata(dtype=np.float32)
        for f in self.inputs.path_files[1:]:
            acc = acc + nib.load(f).get_fdata(dtype=np.float32)

        # preserve exactly the input image space; set_data_dtype clears any
        # residual scaling so values are not re-scaled on write
        hdr = first_nii.header.copy()
        hdr.set_data_dtype(np.float32)
        nib.save(nib.Nifti1Image(acc, first_nii.affine, hdr), out_file)

        # sum the waytotal counts
        waytotal_sum = 0
        for wf in self.inputs.waytotal_files:
            if os.path.exists(wf):
                with open(wf, "r") as file:
                    for line in file.readlines():
                        waytotal_sum += int(line)

        with open(waytotal_sum_file, "w") as file:
            file.write(str(waytotal_sum))

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file):
            out_file = "sum.nii.gz"
        return abspath(out_file)

    def _gen_waytotal_outfilename(self):
        out_file = os.path.basename(self._gen_outfilename())
        return abspath(out_file.replace(".nii.gz", "") + "_waytotal")

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        outputs["waytotal_sum"] = self._gen_waytotal_outfilename()
        return outputs
