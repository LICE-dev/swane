from nipype.interfaces.base import (
    CommandLine,
    CommandLineInputSpec,
    TraitedSpec,
    File,
    traits
)
import os


class SegmentEndocraniumInputSpec(CommandLineInputSpec):
    slicer_cmd = File(
        exists=True,
        mandatory=True,
        desc="Path all'eseguibile Slicer"
    )

    in_file = File(
        exists=True,
        mandatory=True,
        desc="Original CT image",
        argstr="%s",
        position=2
    )

    out_file = File(
        desc="Endocranium mask file name",
        argstr="%s",
        position=3,
        genfile=True
    )

    out_skull = File(
        desc="Skull mask file name",
        argstr="%s",
        position=4,
        genfile=True
    )

    smoothingKernelSize = traits.Float(
        3.0,
        usedefault=True,
        desc="Kernel size in mm",
        argstr="%f",
        position=5
    )


class SegmentEndocraniumOutputSpec(TraitedSpec):
    out_file = File(
        exists=True,
        desc="Endocranium mask"
    )

    out_skull = File(
        exists=True,
        desc="Skull mask"
    )

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
        self._cmd = f"{self.inputs.slicer_cmd} --no-main-window --python-script {worker_path}"

    def _format_arg(self, name, spec, value):
        return super()._format_arg(name, spec, value)

    def _gen_filename(self, name):
        if name == "out_file":
            return os.path.abspath("inskull_mask.nii.gz")
        if name == "out_skull":
            return os.path.abspath("skull_masked_volume.nii.gz")
        return None

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = os.path.abspath(self.inputs.out_file)
        outputs["out_skull"] = os.path.abspath(self.inputs.out_skull)
        return outputs

    @property
    def _command(self):

        return f"{self.inputs.slicer_cmd} --no-main-window --python-script {worker_path}"
