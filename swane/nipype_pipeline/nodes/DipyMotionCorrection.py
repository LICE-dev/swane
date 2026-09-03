# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Between-volumes DWI motion correction with gradient reorientation.

Each diffusion volume is registered to the b0 reference and the gradient
directions are reoriented to compensate for the applied rotations (Leemans &
Jones 2009), using dipy's official ``reorient_bvecs`` helper rather than a
hand-rolled rotation.

Two interchangeable paths sit behind the same interface:

* a **serial** path calling dipy's ``motion_correction`` directly, kept
  permanently reachable as reference and fallback (``parallel=False``);
* a **parallel** path that reproduces ``dipy.align._public.register_dwi_series``
  (dipy is BSD-3-licensed; see ``NOTICE.md``) but dispatches the independent
  per-volume affine registrations across our own process pool, reassembling
  strictly by volume index.

The per-volume affine registration is deterministic, so with the BLAS thread
count pinned identically the parallel path is bit-for-bit equal to the serial
one. Parallelism therefore comes purely from running several worker *processes*,
each with its BLAS backend pinned to a single thread: this keeps the resource
footprint at the declared ``num_threads`` (``num_threads`` processes x 1 thread)
instead of oversubscribing (``num_threads`` processes x ``num_threads`` threads),
and is what makes the serial/parallel oracle exact. The single serial process
uses ``num_threads`` BLAS threads for the same footprint.
"""

import os
import shutil
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from os.path import abspath, basename

import numpy as np
import nibabel as nib
from threadpoolctl import threadpool_limits
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

from dipy.align import motion_correction, affine_registration, register_series
from dipy.align._public import read_img_arr_or_path
from dipy.core.gradients import gradient_table, reorient_bvecs
from dipy.io.gradients import read_bvals_bvecs

# BLAS/OpenMP thread-count environment variables, pinned like the ITK variable
# in AntsN4BiasFieldCorrection so numpy's OpenBLAS backend does not multithread
# invisibly to nipype's resource accounting.
OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"

# The registration pyramid. This is dipy's ``motion_correction`` default with the
# trailing ``affine`` stage DROPPED: between-volumes head motion is rigid, so the
# affine stage only models scaling/shear that head motion cannot produce. Measured
# on both oracle subjects, dropping it leaves the corrected series ~identical
# (series correlation 0.9995 subj1 / 0.9997 subj2, max reoriented-bvec diff <0.005)
# and saves ~30% of the motion-correction time. The cost is that the affine stage
# was also the dipy branch's only geometric eddy-distortion correction, so eddy
# distortion is now left uncorrected -- a declared asymmetry vs the FSL eddy path
# (spec section 5). Both the serial and parallel paths read this constant, so they
# stay bit-for-bit equivalent.
DEFAULT_PIPELINE = ["center_of_mass", "translation", "rigid"]


def _register_one_volume(index, moving, moving_affine, static, static_affine, pipeline):
    """Register one moving volume to the static reference (BLAS pinned to 1).

    Returns ``(index, transformed_volume, reg_affine)``. The index travels with
    the payload so the driver can reassemble results by volume position no
    matter what order the workers finish in.
    """
    with threadpool_limits(limits=1):
        transformed, reg_affine = affine_registration(
            moving,
            static,
            moving_affine=moving_affine,
            static_affine=static_affine,
            pipeline=pipeline,
        )
    return index, transformed, reg_affine


def _register_moving_volumes(
    moving_data,
    static,
    affine,
    pipeline,
    num_threads,
    register_fn=None,
    use_processes=True,
):
    """Register every volume of ``moving_data`` to ``static`` over a pool.

    Results are placed strictly by the index returned with each payload, so a
    worker finishing out of order can never scramble the series. ``register_fn``
    and ``use_processes`` are injection points for the reassembly unit test.
    """
    register_fn = register_fn or _register_one_volume
    n_vols = moving_data.shape[-1]
    xformed = np.zeros(moving_data.shape)
    affines = np.zeros((4, 4, n_vols))

    executor_cls = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    max_workers = max(1, int(num_threads))
    with executor_cls(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                register_fn,
                index,
                moving_data[..., index],
                affine,
                static,
                affine,
                pipeline,
            )
            for index in range(n_vols)
        ]
        for future in as_completed(futures):
            index, transformed, reg_affine = future.result()
            xformed[..., index] = transformed
            affines[..., index] = reg_affine

    return xformed, affines


def _serial_motion_correction(img, gtab, blas_threads=1):
    """Reference path: dipy's ``motion_correction`` with BLAS pinned.

    Returns ``(registered_image, affine_array)`` where ``affine_array`` has
    shape ``(4, 4, n_volumes)`` and covers **all** volumes, b0s included.

    ``pipeline=DEFAULT_PIPELINE`` is passed explicitly: dipy's ``motion_correction``
    default still carries the trailing ``affine`` stage we drop, so relying on its
    default would make the serial path disagree with the parallel one (which reads
    DEFAULT_PIPELINE) and break the equivalence oracle.
    """
    with threadpool_limits(limits=max(1, int(blas_threads))):
        return motion_correction(img, gtab, pipeline=DEFAULT_PIPELINE)


def _parallel_motion_correction(img, gtab, num_threads):
    """Parallel path reproducing ``register_dwi_series`` over our own pool.

    Mirrors dipy's ``dipy.align._public.register_dwi_series`` (BSD-3) so the b0
    reference is built identically, then registers the diffusion-weighted
    volumes across a process pool. The returned ``(image, affine_array)`` is
    bit-for-bit equal to the serial path when BLAS threads match.
    """
    data, affine = read_img_arr_or_path(img)
    b0s_mask = gtab.b0s_mask

    if np.sum(b0s_mask) > 1:
        # Register the b0 volumes to each other and average, exactly as dipy.
        b0_img = nib.Nifti1Image(data[..., b0s_mask], affine)
        with threadpool_limits(limits=1):
            trans_b0, b0_affines = register_series(
                b0_img, ref=0, pipeline=DEFAULT_PIPELINE
            )
        ref_data = np.mean(trans_b0, -1, keepdims=True)
    else:
        trans_b0 = ref_data = data[..., b0s_mask]
        b0_affines = np.eye(4)[..., np.newaxis]

    moving_data = data[..., ~b0s_mask]
    static = ref_data.squeeze()

    xformed, moving_affines = _register_moving_volumes(
        moving_data, static, affine, DEFAULT_PIPELINE, num_threads
    )

    affine_array = np.zeros((4, 4, data.shape[-1]))
    affine_array[..., b0s_mask] = b0_affines
    affine_array[..., ~b0s_mask] = moving_affines

    data_array = np.zeros(data.shape)
    data_array[..., b0s_mask] = trans_b0
    data_array[..., ~b0s_mask] = xformed

    return nib.Nifti1Image(data_array, affine), affine_array


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyMotionCorrectionInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input 4D DWI image")
    bval = File(exists=True, mandatory=True, desc="the b-values file")
    bvec = File(exists=True, mandatory=True, desc="the b-vectors file")
    num_threads = traits.Int(
        nohash=True, desc="number of worker processes / pinned BLAS threads"
    )
    parallel = traits.Bool(
        True,
        usedefault=True,
        desc="use the parallel process-pool path (False keeps the serial "
        "dipy path as a reference/fallback)",
    )
    out_file = File(desc="the motion-corrected 4D DWI image")
    out_bvec = File(desc="the reoriented b-vectors file")
    out_bval = File(desc="the passed-through b-values file")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyMotionCorrectionOutputSpec(TraitedSpec):
    out_file = File(desc="the motion-corrected 4D DWI image")
    out_bvec = File(desc="the reoriented b-vectors file")
    out_bval = File(desc="the passed-through b-values file")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyMotionCorrection(BaseInterface):
    """
    Between-volumes DWI motion correction with gradient reorientation.

    Registers each diffusion volume to the b0 reference (dipy ``motion_correction``)
    and reorients the gradient directions with ``reorient_bvecs`` to compensate
    for the applied rotations. The parallel path distributes the per-volume
    registrations over our own process pool and is bit-for-bit equivalent to the
    serial reference path.

    """

    input_spec = DipyMotionCorrectionInputSpec
    output_spec = DipyMotionCorrectionOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )

        img = nib.load(self.inputs.in_file)
        bvals, bvecs = read_bvals_bvecs(self.inputs.bval, self.inputs.bvec)
        gtab = gradient_table(bvals, bvecs=bvecs)

        # Pin the process-level thread environment to the declared count, saving
        # and restoring like the ITK variable in AntsN4BiasFieldCorrection.
        previous = {
            var: os.environ.get(var) for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR)
        }
        for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR):
            os.environ[var] = str(num_threads)
        try:
            if self.inputs.parallel:
                registered_img, affine_array = _parallel_motion_correction(
                    img, gtab, num_threads
                )
            else:
                registered_img, affine_array = _serial_motion_correction(
                    img, gtab, blas_threads=num_threads
                )
        finally:
            for var, val in previous.items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val

        # Save the motion-corrected 4D image, preserving the input dtype.
        registered_img = nib.Nifti1Image(
            registered_img.get_fdata().astype(img.get_data_dtype()),
            img.affine,
            img.header,
        )
        nib.save(registered_img, self._gen_outfilename("out_file", "moco_"))

        # Reorient the gradients. THE INDEXING TRAP: motion_correction returns
        # affines for *all* volumes, while reorient_bvecs expects only the
        # non-b0 ones, ordered as gtab.bvecs[~gtab.b0s_mask]. Passing the full
        # array would silently misalign every gradient.
        reoriented = reorient_bvecs(gtab, affine_array[..., ~gtab.b0s_mask])
        out_bvec = self._gen_outfilename("out_bvec", "moco_", ".bvec")
        np.savetxt(out_bvec, reoriented.bvecs.T, fmt="%.10f")

        # Pass the b-values through unchanged.
        shutil.copyfile(
            self.inputs.bval, self._gen_outfilename("out_bval", "moco_", ".bval")
        )

        return runtime

    def _gen_outfilename(self, trait_name, prefix, suffix=None):
        out_file = getattr(self.inputs, trait_name)
        if not isdefined(out_file):
            base = basename(self.inputs.in_file)
            if suffix is not None:
                # Replace the NIfTI extension with the requested one.
                for ext in (".nii.gz", ".nii"):
                    if base.endswith(ext):
                        base = base[: -len(ext)] + suffix
                        break
                else:
                    base = base + suffix
            out_file = prefix + base
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file"] = self._gen_outfilename("out_file", "moco_")
        outputs["out_bvec"] = self._gen_outfilename("out_bvec", "moco_", ".bvec")
        outputs["out_bval"] = self._gen_outfilename("out_bval", "moco_", ".bval")
        return outputs
