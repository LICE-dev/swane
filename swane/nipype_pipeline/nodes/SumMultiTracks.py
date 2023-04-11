# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
import os

from nipype.interfaces.fsl import BinaryMaths
from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, InputMultiPath, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class SumMultiTracksInputSpec(BaseInterfaceInputSpec):
    path_files = InputMultiPath(File(exists=True), mandatory=True, desc="list of path file to sum togheter")
    waytotal_files = InputMultiPath(File(exists=True), mandatory=True, desc="list of waytotal files to sum togheter")
    out_file = File(desc='the output image')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SumMultiTracksOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc='the output image')
    waytotal_sum = File(exists=True, desc='the output waytotal file')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class SumMultiTracks(BaseInterface):
    """
    Merges results from multiple tractography runs.

    """
    
    input_spec = SumMultiTracksInputSpec
    output_spec = SumMultiTracksOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()
        waytotal_sum_file = self._gen_waytotal_outfilename()

        steps = len(self.inputs.path_files) - 1
        sum_loop = [None] * steps
        sum_res = [None] * steps

        waytotal_sum = 0

        for x in range(steps):

            # SUM FTP_PATHS
            sum_loop[x] = BinaryMaths()
            sum_loop[x].inputs.operation = "add"

            if x == 0:
                sum_loop[x].inputs.in_file = self.inputs.path_files[x]
            else:
                sum_loop[x].inputs.in_file = sum_res[(x - 1)].outputs.out_file

            sum_loop[x].inputs.operand_file = self.inputs.path_files[(x + 1)]

            if x == (steps - 1):
                sum_loop[x].inputs.out_file = self.inputs.out_file

            sum_res[x] = sum_loop[x].run()

            # SUM WAYTOTAL
            if os.path.exists(self.inputs.waytotal_files[x]):
                with open(self.inputs.waytotal_files[x], 'r') as file:
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
        out_file = os.path.basename(self.inputs.out_file)
        if not isdefined(out_file):
            out_file = "waytotal"
        else:
            out_file = out_file.replace(".nii.gz", "") + "_waytotal"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        outputs['waytotal_sum'] = self._gen_waytotal_outfilename()
        return outputs
