# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
from nipype.interfaces.freesurfer.base import FSTraitedSpec, FSCommand
from nipype.interfaces.base import (
    TraitedSpec,
    File,
    traits,
    isdefined,
    Undefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSTraitedSpec)  -*-
class SynthSegInputSpec(FSTraitedSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        argstr="--i %s",
        desc="image to segment",
    )
    out_file = File(
        argstr="--o %s",
        hash_files=False,
        name_source=["in_file"],
        name_template="%s_segmentation",
        keep_extension=True,
        desc="name of output skull stripped image",
    )
    parcellation = traits.Bool(desc="perform cortical parcellation in addition to whole-brain segmentation", argstr="--parc")
    robust = traits.Bool(desc="use the variant for increased robustness", argstr="--robust")
    fast = traits.Bool(desc="disable some postprocessing operations for faster prediction", argstr="--fast")
    use_cpu = traits.Bool(desc="run on the CPU rather than the GPU", argstr="--cpu")
    use_gpu = traits.Bool(True, usedefault=True, desc="run on the GPU rather than the GPU")


    version_1 = traits.Bool(desc="run the first version of SynthSeg (SynthSeg 1.0)", argstr="--v1")
    ct = traits.Bool(desc="processing CT scans ", argstr="--ct")
    photo = traits.Bool(desc="processing stacks of 3D reconstructed dissection photos", argstr="--photo")

    volume_file = File(
        argstr="--vol %s",
        desc="CSV file where volumes for all segmented regions will be saved",
    )
    qc_file = File(
        argstr="--qc %s",
        desc="CSV file where QC scores will be saved",
    )
    post_file = File(
        argstr="--post %s",
        desc="path where the output 3D posterior probabilities will be saved",
    )
    resampled_file = File(
        argstr="--resample %s",
        desc="save the original images resampled at 1mm",
    )
    crop = traits.Int(
        argstr="--crop %d",
        desc="crop the inputs to a given shape before segmentation. This must be divisible by 32",
    )
    num_threads = traits.Int(
        argstr="--threads %d",
        hash_file=False,
        desc="number of threads to be used by Tensorflow when using the CPU version",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class SynthSegOutputSpec(TraitedSpec):
    out_file = File(desc="path/name of segmentation file")
    volume_file = File(desc="path/name of CSV volume file (if generated)")
    qc_file = File(desc="path/name of CSV QC score file (if generated)")
    post_file = File(desc="path/name 3D posterior probabilities file (if generated)")
    resampled_file = File(desc="path/name resampled image file (if generated)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.base.FSCommand)  -*-
class SynthSeg(FSCommand):
    _cmd = "mri_synthseg"
    input_spec = SynthSegInputSpec
    output_spec = SynthSegOutputSpec

    def __init__(self, **inputs):
        super().__init__(**inputs)
        self.inputs.on_trait_change(self._use_gpu_update, "use_gpu")
        self.inputs.on_trait_change(self._use_cpu_update, "use_cpu")
        self.inputs.on_trait_change(self._num_threads_update, "num_threads")

    def _use_gpu_update(self):
        if isdefined(self.inputs.use_gpu):
            if self.inputs.use_gpu:
                self.inputs.use_cpu = Undefined
                if isdefined(self.inputs.num_threads):
                    self.inputs.num_threads = 1
            else:
                self.inputs.use_gpu = Undefined
                self.inputs.use_cpu = True

    def _use_cpu_update(self):
        if isdefined(self.inputs.use_gpu):
            if self.inputs.use_cpu:
                self.inputs.use_gpu = Undefined
            else:
                self.inputs.use_cpu = Undefined
                self.inputs.use_gpu = True
                if isdefined(self.inputs.num_threads):
                    self.inputs.num_threads = 1

    def _num_threads_update(self):
        if isdefined(self.inputs.use_gpu) and self.inputs.use_gpu:
            self.inputs.num_threads = Undefined

    def _list_outputs(self):
        outputs = super()._list_outputs()
        for name in ["volume_file", "qc_file", "post_file", "resampled_file"]:
            if isdefined(getattr(self.inputs,name)):
                outputs[name] = getattr(self.inputs,name)
        return outputs
    