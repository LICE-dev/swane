from nipype.interfaces.base import (
    CommandLine,
    CommandLineInputSpec,
    TraitedSpec,
    File,
    traits,
)
import os


class SegmentEndocraniumInputSpec(CommandLineInputSpec):

    slicer_cmd = File(exists=True, mandatory=True, desc="Slicer executable path")

    in_file = File(
        exists=True, mandatory=True, desc="Original CT image", argstr="--input %s"
    )

    out_file = File(
        desc="Endocranium mask file name", argstr="--output %s", genfile=True
    )

    smoothingKernelSize = traits.Float(
        3.0, usedefault=True, desc="Kernel size in mm", argstr="--kernel-mm %.2f"
    )

    oversampling = traits.Float(
        1.0,
        usedefault=True,
        desc="Wrap solidify oversampling",
        argstr="--oversampling %.2f",
    )

    iterations = traits.Int(
        3, usedefault=True, desc="Shrinkwrap iterations", argstr="--iterations %d"
    )

    skull_threshold = traits.Int(
        -1,
        usedefault=True,
        desc="Threshold for skull segmentation, -1 use Slicer maximum entropy automatic thresholding",
        argstr="--skull_threshold %d",
    )


class SegmentEndocraniumOutputSpec(TraitedSpec):
    out_file = File(exists=True, desc="Endocranium mask")


class SegmentEndocranium(CommandLine):
    input_spec = SegmentEndocraniumInputSpec
    output_spec = SegmentEndocraniumOutputSpec

    _cmd = "echo"

    def __init__(self, **inputs):
        super().__init__(**inputs)
        self.inputs.on_trait_change(self._cmd_update, "slicer_cmd")

    def _cmd_update(self):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        worker_path = os.path.abspath(
            os.path.join(this_dir, "..", "..", "workers", "slicer_seg_endocranium.py")
        )

        if not os.path.exists(worker_path):
            raise FileNotFoundError(f"Worker not found: {worker_path}")
        self._cmd = f"{self.inputs.slicer_cmd} --no-splash --no-main-window --python-script {worker_path}"

    def _format_arg(self, name, spec, value):
        return super()._format_arg(name, spec, value)

    def _gen_filename(self, name):
        if name == "out_file":
            return os.path.abspath("inskull_mask.nii.gz")
        return None

    def _list_outputs(self):
        outputs = self.output_spec().get()

        # Usa genfile, NON self.inputs.out_file
        outputs["out_file"] = self._gen_filename("out_file")

        return outputs
