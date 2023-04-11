# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
import os
import glob
from nipype.interfaces.base import (traits, TraitedSpec, CommandLineInputSpec, CommandLine, File, Directory, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.CommandLineInputSpec)  -*-
class SegmentHAInputSpec(CommandLineInputSpec):
    subject_id = traits.Str(
        "recon_all", mandatory=True, position=0, argstr="%s", desc="subject name", usedefault=True
    )
    subjects_dir = Directory(
        exists=True,
        mandatory=True,
        position=1,
        argstr="%s",
        hash_files=False,
        desc="path to subjects directory",
        genfile=True,
    )
    num_threads = traits.Int(argstr="")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SegmentHAOutputSpec(TraitedSpec):
    lh_hippoAmygLabels = File(desc="Discrete segmentation volumes at subvoxel resolution")
    rh_hippoAmygLabels = File(desc="Discrete segmentation volumes at subvoxel resolution")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.CommandLine)  -*-
class SegmentHA(CommandLine):
    """
    Executes the segmentHA_T1.sh FreeSurfer command.

    """
    
    _cmd = 'segmentHA_T1.sh'
    input_spec = SegmentHAInputSpec
    output_spec = SegmentHAOutputSpec

    def _list_outputs(self):
        base = os.path.join(self.inputs.subjects_dir, self.inputs.subject_id, "mri")
        lh = ''
        rh = ''

        src = glob.glob(os.path.abspath(os.path.join(base, "lh.hippoAmygLabels-T1.v[0-9][0-9].mgz")))
        if len(src) == 1:
            lh = src[0]

        src = glob.glob(os.path.abspath(os.path.join(base, "rh.hippoAmygLabels-T1.v[0-9][0-9].mgz")))
        if len(src) == 1:
            rh = src[0]

        return {
            'lh_hippoAmygLabels': lh,
            'rh_hippoAmygLabels': rh
        }

    def _parse_inputs(self, skip=None):
        """
        Custom implementation of _parse_inputs func to manage multithreading.

        """

        if isdefined(self.inputs.num_threads):
            skip = ["num_threads"]
            self.n_procs = self.inputs.num_threads
            self.inputs.environ["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = "%d" % self.inputs.num_threads

        parse = super(SegmentHA, self)._parse_inputs(skip)

        # Delete lock file if exists from previous execution
        ex_path = abspath(
            os.path.join(self.inputs.subjects_dir, self.inputs.subject_id, "scripts/IsRunningHPsubT1.lh+rh"))

        if os.path.exists(ex_path):
            os.remove(ex_path)

        return parse
