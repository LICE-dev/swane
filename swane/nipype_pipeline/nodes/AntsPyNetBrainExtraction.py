# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
from os.path import abspath

from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

# antspyx and antspynet are imported lazily inside _run_interface, as in
# AntsN4BiasFieldCorrection, so importing this module never loads tensorflow.

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AntsPyNetBrainExtractionInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input image")
    modality = traits.Str(
        mandatory=True,
        desc="antspynet brain_extraction modality key (e.g. t1, flair, t2, bold)",
    )
    out_file = File(desc="the skull-stripped brain image")
    mask_file = File(desc="the binary brain mask")
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AntsPyNetBrainExtractionOutputSpec(TraitedSpec):
    out_file = File(desc="the skull-stripped brain image")
    mask_file = File(desc="the binary brain mask")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AntsPyNetBrainExtraction(BaseInterface):
    """
    Skull-strip an image with antspynet deep-learning brain extraction.

    antspynet.brain_extraction returns a probability image in the input grid;
    this node binarizes it at 0.5, writes the mask, and writes the input masked
    by it as the brain image.
    """

    input_spec = AntsPyNetBrainExtractionInputSpec
    output_spec = AntsPyNetBrainExtractionOutputSpec

    def _run_interface(self, runtime):
        import ants
        import antspynet

        out_file = self._gen_outfilename()
        img = ants.image_read(self.inputs.in_file, pixeltype="float")

        previous_threads = os.environ.get(ITK_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[ITK_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            prob = antspynet.brain_extraction(img, modality=self.inputs.modality)
        finally:
            if previous_threads is None:
                os.environ.pop(ITK_THREADS_VAR, None)
            else:
                os.environ[ITK_THREADS_VAR] = previous_threads

        mask = prob.new_image_like((prob.numpy() >= 0.5).astype("float32"))

        if isdefined(self.inputs.mask_file):
            ants.image_write(mask, abspath(self.inputs.mask_file))

        ants.image_write(img * mask, out_file)
        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_file
        if not isdefined(out_file) and isdefined(self.inputs.in_file):
            out_file = "brain_" + os.path.basename(self.inputs.in_file)
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename()
        if isdefined(self.inputs.mask_file):
            outputs["mask_file"] = abspath(self.inputs.mask_file)
        return outputs
