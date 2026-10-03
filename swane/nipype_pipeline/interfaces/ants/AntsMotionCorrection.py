# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
import subprocess
import sys
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
)

# Fixed seed for the random metric sampling of the ANTs registration. Any
# non-zero integer is valid for antsRegistration --random-seed; 123 is the
# default seed of antspyx's own deterministic mode (ants.config).
DEFAULT_RANDOM_SEED = 123


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AntsMotionCorrectionInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="4D EPI NIfTI image")
    random_seed = traits.Int(
        DEFAULT_RANDOM_SEED,
        usedefault=True,
        desc="Non-zero seed of the random metric sampling of every per-volume "
        "registration; with single-threaded ITK it makes the output "
        "reproducible run to run",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AntsMotionCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="Motion corrected 4D image")
    par_file = File(desc="Realignment parameters (T x 6, SPM order)")


def _motion_correct(in_file, out_dir, random_seed):
    """Run the ANTs rigid motion correction (called in a child interpreter).

    Writes ``mc.nii.gz`` and ``motion.par`` in ``out_dir``. The caller starts
    the child with ``ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1`` in its
    environment, see :class:`AntsMotionCorrection`.
    """
    import locale
    import numpy as np
    import nibabel as nib
    import ants

    # ANTs/ITK C++ library expects standard 'C' numeric locale with '.' decimal points.
    # When running under a GUI process (PySide6/Qt) with non-English system locales,
    # LC_NUMERIC can be set to comma-based formats (e.g. it_IT), causing ITK
    # float parsing to fail. Restore LC_NUMERIC to "C".
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass

    # ants.registration passes this module setting as --random-seed to
    # antsRegistration; it lives only in this child process.
    ants.config._random_seed = int(random_seed)

    # Determine fixed volume (middle volume)
    img_nib = nib.load(in_file)
    mid = int(img_nib.shape[3] / 2)

    img = ants.image_read(in_file)
    fixed = img.ndimage_to_list()[mid]

    # Run ANTs motion correction
    res = ants.motion_correction(img, fixed=fixed, type_of_transform="Rigid")

    # Save motion corrected image
    out_file = os.path.join(out_dir, "mc.nii.gz")
    ants.image_write(res["motion_corrected"], out_file)

    # Decompose parameters
    params = []
    for m in res["motion_parameters"]:
        mat_path = m[0]
        p = np.asarray(ants.read_transform(mat_path).parameters, dtype=float)
        R = p[:9].reshape(3, 3)
        t = p[9:12]
        sy = float(np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2))
        if sy > 1e-6:
            rx = np.arctan2(R[2, 1], R[2, 2])
            ry = np.arctan2(-R[2, 0], sy)
            rz = np.arctan2(R[1, 0], R[0, 0])
        else:
            rx = np.arctan2(-R[1, 2], R[1, 1])
            ry = np.arctan2(-R[2, 0], sy)
            rz = 0.0
        params.append([t[0], t[1], t[2], rx, ry, rz])

    params = np.array(params, dtype=float)
    par_file = os.path.join(out_dir, "motion.par")
    np.savetxt(par_file, params, fmt="%.10f")


# Child interpreter entry point: arguments are in_file, out_dir, random_seed,
# package_root.
# Makes this same swane package importable in the child. The package root
# (argv[4]) is added only when it is not on the interpreter's default path:
# for an installed SWANe it is site-packages, already on the path after the
# standard library, and moving it ahead (as PYTHONPATH would) could let a
# stdlib-named module in site-packages shadow the standard library. A source
# checkout is not on the default path and is inserted after the script
# directory, where PYTHONPATH entries would go.
_CHILD_BOOTSTRAP = (
    "import os, sys\n"
    "_root = os.path.realpath(sys.argv[4])\n"
    "if _root not in [os.path.realpath(p) for p in sys.path if p]:\n"
    "    sys.path.insert(1, _root)\n"
)

_CHILD_CODE = _CHILD_BOOTSTRAP + (
    "from swane.nipype_pipeline.interfaces.ants.AntsMotionCorrection import "
    "_motion_correct\n"
    "_motion_correct(sys.argv[1], sys.argv[2], int(sys.argv[3]))\n"
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AntsMotionCorrection(BaseInterface):
    """
    AntsMotionCorrection

    Rigid realignment via the ANTs framework (Avants et al. 2008).
    Uses antspy Rigid motion correction with a middle-volume fixed reference.

    Reproducibility: the registrations run with a fixed random seed
    (``random_seed``) and a single ITK thread, so the same input always gives
    the same output; the node therefore uses one core. Both are needed: the
    seed fixes the random metric sampling, the single thread fixes the order of
    the multithreaded metric sums. ITK reads ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS
    once per process, the first time its threader is used, and caches it, so
    setting it in a process that already ran an ITK filter (a Nipype worker, a
    test session) has no effect. The registration therefore runs in a fresh
    child interpreter started with that variable set; the environment and the
    ants module state of the calling process are never modified.

    References:
    - Avants BB, Epstein CL, Grossman M, Gee JC (2008). Symmetric diffeomorphic
      image registration with cross-correlation. Medical Image Analysis 12:26-41.
    - Tustison NJ, Cook PA, Holbrook AJ, et al. (2021). The ANTsX ecosystem for
      quantitative biological and medical imaging. Scientific Reports 11:9068.
    """

    input_spec = AntsMotionCorrectionInputSpec
    output_spec = AntsMotionCorrectionOutputSpec

    def _run_interface(self, runtime):
        # A new interpreter, not a forked process: a fork would inherit the ITK
        # thread count already cached by this process.
        env = os.environ.copy()
        env["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = "1"
        # Import this same swane package in the child, installed or not
        # (see _CHILD_BOOTSTRAP).
        package_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                _CHILD_CODE,
                os.path.abspath(self.inputs.in_file),
                runtime.cwd,
                str(self.inputs.random_seed),
                package_root,
            ],
            env=env,
            cwd=runtime.cwd,
            capture_output=True,
            text=True,
        )
        runtime.stdout = proc.stdout
        runtime.stderr = proc.stderr
        if proc.returncode != 0:
            raise RuntimeError(
                "ANTs motion correction failed (exit code %d):\n%s"
                % (proc.returncode, proc.stderr[-4000:])
            )
        self._out_file = os.path.join(runtime.cwd, "mc.nii.gz")
        self._par_file = os.path.join(runtime.cwd, "motion.par")
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_file"] = self._out_file
        outputs["par_file"] = self._par_file
        return outputs
