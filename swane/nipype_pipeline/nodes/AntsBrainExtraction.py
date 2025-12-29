import os
import ants

from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits, isdefined
)
class BrainExtractionAntsPyInputSpec(BaseInterfaceInputSpec):
    """
    Brain extraction using ANTsPy.
    Exactly one of in_file or in_image must be provided.
    """

    in_file = File(
        exists=True,
        xor=["in_image"],
        requires=["in_image"],
        desc="Input anatomical image (NIfTI file)"
    )

    in_image = traits.Any(
        xor=["in_file"],
        requires=["in_file"],
        desc="Input anatomical image as ants.ANTsImage"
    )

    modality = traits.Enum(
        "t1", "t2", "flair", "bold", "dwi",
        usedefault=True,
        desc="Imaging modality"
    )

    antsxnet = traits.Bool(
        True,
        usedefault=True,
        desc="Use ANTsXNet (deep learning) for brain extraction"
    )

    return_brainmask = traits.Bool(
        True,
        usedefault=True,
        desc="Return brain mask"
    )

    write_outputs = traits.Bool(
        True,
        usedefault=True,
        desc="Write output images to disk"
    )

    out_prefix = traits.Str(
        "BrainExtraction",
        usedefault=True,
        desc="Prefix for output files (used only if write_outputs=True)"
    )

    num_threads = traits.Int(
        desc="Number of threads for ANTs"
    )

    debug = traits.Bool(
        False,
        usedefault=True,
        desc="Verbose output"
    )


class BrainExtractionAntsPyOutputSpec(TraitedSpec):
    # In-memory outputs
    brain_image = traits.Any(desc="Brain-extracted image (ANTsImage)")
    brain_mask = traits.Any(desc="Brain mask (ANTsImage)")

    # Optional file outputs
    brain_image_file = File(desc="Skull-stripped image file")
    brain_mask_file = File(desc="Brain mask file")


class BrainExtractionAntsPy(BaseInterface):

    input_spec = BrainExtractionAntsPyInputSpec
    output_spec = BrainExtractionAntsPyOutputSpec

    def _run_interface(self, runtime):

        if isdefined(self.inputs.num_threads):
            ants.set_num_threads(self.inputs.num_threads)

        # Load input image
        img = (
            ants.image_read(self.inputs.in_file)
            if isdefined(self.inputs.in_file)
            else self.inputs.in_image
        )

        # Run brain extraction
        result = ants.brain_extraction(
            image=img,
            modality=self.inputs.modality,
            antsxnet=self.inputs.antsxnet,
            return_brainmask=self.inputs.return_brainmask,
            verbose=self.inputs.debug
        )

        # In-memory outputs
        self._brain = result["brain"]
        self._mask = result.get("brainmask", None)

        # Optional file outputs (SIDE EFFECTS LIVE HERE)
        self._brain_file = None
        self._mask_file = None

        if self.inputs.write_outputs:
            prefix = os.path.abspath(self.inputs.out_prefix)

            self._brain_file = prefix + "_Brain.nii.gz"
            ants.image_write(self._brain, self._brain_file)

            if self._mask is not None:
                self._mask_file = prefix + "_BrainMask.nii.gz"
                ants.image_write(self._mask, self._mask_file)

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()

        # In-memory outputs
        outputs["brain_image"] = self._brain
        if self._mask is not None:
            outputs["brain_mask"] = self._mask

        # File outputs (only if generated)
        if self._brain_file is not None:
            outputs["brain_image_file"] = self._brain_file

        if self._mask_file is not None:
            outputs["brain_mask_file"] = self._mask_file

        return outputs

