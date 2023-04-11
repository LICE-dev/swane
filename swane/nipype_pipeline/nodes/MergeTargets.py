# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
from nipype.interfaces.base import (BaseInterface, BaseInterfaceInputSpec, TraitedSpec, InputMultiPath, File, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class MergeTargetsInputSpec(BaseInterfaceInputSpec):
    target_files = InputMultiPath(File(exists=True), mandatory=True, desc="list of path file to merge in txt")
    out_file = File(desc='the output file name')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class MergeTargetsOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc='the output txt file')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class MergeTargets(BaseInterface):
    """
    Creates a .txt file from an array.

    """
    
    input_spec = MergeTargetsInputSpec
    output_spec = MergeTargetsOutputSpec

    def _run_interface(self, runtime):
        self.inputs.out_file = self._gen_outfilename()

        lines = "\n".join(self.inputs.target_files)

        with open(self.inputs.out_file, "w") as file:
            file.write(lines)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file):
            out_file = "targets.txt"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['out_file'] = self._gen_outfilename()
        return outputs
