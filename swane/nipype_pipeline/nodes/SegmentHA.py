# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
import os
import glob
from nipype.interfaces.base import (traits, TraitedSpec, CommandLineInputSpec, CommandLine, File, Directory, isdefined)


# IMPLEMENTAZIONE DI SEGMENT_HA
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
    # lh_hippoSfVolumes = File(desc="Estimated volumes of the hippocampal substructures and of the whole hippocampus")
    # lh_amygNucVolumes = File(desc="Estimated volumes of the nuclei of the amygdala and of the whole amygdala")
    lh_hippoAmygLabels = File(desc="Discrete segmentation volumes at subvoxel resolution")
    # lh_hippoAmygLabels_hierarchy = File(desc="Segmentations with the different hierarchy levels")
    # rh_hippoSfVolumes = File(desc="Estimated volumes of the hippocampal substructures and of the whole hippocampus")
    # rh_amygNucVolumes = File(desc="Estimated volumes of the nuclei of the amygdala and of the whole amygdala")
    rh_hippoAmygLabels = File(desc="Discrete segmentation volumes at subvoxel resolution")
    # rh_hippoAmygLabels_hierarchy = File(desc="Segmentations with the different hierarchy levels")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.CommandLine)  -*-
class SegmentHA(CommandLine):
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

        # Get the attribute saved during _run_interface
        # return {'lh_hippoSfVolumes':abspath(os.path.join(base,"lh.hippoSfVolumes-T1.v21.txt:")),
        #         'rh_hippoSfVolumes':abspath(os.path.join(base,"lh.hippoSfVolumes-T1.v21.txt:")),
        #         'lh_amygNucVolumes':abspath(os.path.join(base,"lh.amygNucVolumes-T1.v21.txt")),
        #         'rh_amygNucVolumes':abspath(os.path.join(base,"rh.amygNucVolumes-T1.v21.txt")),
        #         'lh_hippoAmygLabels':abspath(os.path.join(base,"lh.hippoAmygLabels-T1.v21.mgz")),
        #         'rh_hippoAmygLabels':abspath(os.path.join(base,"/rh.hippoAmygLabels-T1.v21.mgz")),
        #         'lh_hippoAmygLabels_hierarchy':abspath(os.path.join(base,"lh.hippoAmygLabels-T1.v21.[hierarchy].mgz")),
        #         'rh_hippoAmygLabels_hierarchy':abspath(os.path.join(base,"rh.hippoAmygLabels-T1.v21.[hierarchy].mgz"))
        #         }

        return {
            'lh_hippoAmygLabels': lh,
            'rh_hippoAmygLabels': rh
        }

    def _parse_inputs(self, skip=None):
        # ABILITO LA VARIABILE PER IL MULTITHREAD E IGNORO L'INPUT
        if isdefined(self.inputs.num_threads):
            skip = ["num_threads"]
            self.inputs.environ["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = "%d" % self.inputs.num_threads

        parse = super(SegmentHA, self)._parse_inputs(skip)

        # se è rimasto il file di lock da precedente esecuzione, lo cancello
        exPath = abspath(
            os.path.join(self.inputs.subjects_dir, self.inputs.subject_id, "scripts/IsRunningHPsubT1.lh+rh"))

        if os.path.exists(exPath):
            os.remove(exPath)

        return parse
