from nipype.interfaces.base import (
    CommandLine,
    CommandLineInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)
import os

from swane.patches.windows_compat import cmdline_quote
from swane.utils.slicer_isolation import isolation_args


class SegmentEndocraniumInputSpec(CommandLineInputSpec):

    slicer_cmd = File(exists=True, mandatory=True, desc="Slicer executable path")

    # Not hashed: the folders depend on where Slicer is installed, not on the
    # result, so moving Slicer must not rerun the node.
    module_paths = traits.List(
        traits.Str(),
        mandatory=True,
        nohash=True,
        desc="Module folders of the Slicer extensions the worker needs, as "
        "recorded by the Slicer check (Slicer runs isolated from the user's "
        "settings, slicerrc and extra modules)",
    )

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
        self.inputs.on_trait_change(
            self._cmd_update, "slicer_cmd,module_paths,module_paths_items"
        )
        if isdefined(self.inputs.slicer_cmd):
            self._cmd_update()

    def _cmd_update(self):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        worker_path = os.path.abspath(
            os.path.join(
                this_dir, "..", "..", "..", "workers", "slicer_seg_endocranium.py"
            )
        )

        if not os.path.exists(worker_path):
            raise FileNotFoundError(f"Worker not found: {worker_path}")
        # nipype runs _cmd through a shell: quote both paths (Slicer's install
        # dir contains a space on Windows). cmdline_quote matches the quoting
        # SWANe's Nipype patch uses for every other argument on each platform.
        module_paths = (
            self.inputs.module_paths if isdefined(self.inputs.module_paths) else []
        )
        isolation = " ".join(
            cmdline_quote(str(arg)) for arg in isolation_args(module_paths)
        )
        self._cmd = (
            f"{cmdline_quote(str(self.inputs.slicer_cmd))} --no-splash "
            f"--no-main-window {isolation} "
            f"--python-script {cmdline_quote(worker_path)}"
        )

    def _run_interface(self, runtime):
        missing = [p for p in self.inputs.module_paths if not os.path.isdir(p)]
        if not self.inputs.module_paths or missing:
            # Isolated Slicer would start without the Wrap Solidify effect and
            # fail deep inside the worker: say what is wrong instead.
            raise RuntimeError(
                "3D Slicer extension module folders are unknown or missing "
                f"({', '.join(missing) or 'none recorded'}): repeat the 3D Slicer "
                "check from SWANe, then rerun the workflow."
            )
        return super()._run_interface(runtime)

    def _format_arg(self, name, spec, value):
        return super()._format_arg(name, spec, value)

    def _gen_filename(self, name):
        if name == "out_file":
            return os.path.abspath("inskull_mask.nii.gz")
        return None

    def _list_outputs(self):
        outputs = self.output_spec().get()

        # Use genfile, NOT self.inputs.out_file
        outputs["out_file"] = self._gen_filename("out_file")

        return outputs
