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

import multiprocessing
import os
import shutil
import sys
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
# trailing ``affine`` stage omitted: between-volumes head motion is rigid, so the
# affine stage only models scaling/shear that head motion cannot produce.
# Omitting it saves execution time while preserving series fidelity.
# The cost is that the affine stage was also the dipy branch's only geometric
# eddy-distortion correction, so eddy distortion is now left uncorrected -- a
# declared asymmetry vs the FSL eddy path.
# Both the serial and parallel paths read this constant, so they stay bit-for-bit
# equivalent.
DEFAULT_PIPELINE = ["center_of_mass", "translation", "rigid"]

# Module-level globals populated by ``_worker_initializer`` in each worker.
# Under ``spawn`` (Windows/macOS) each worker re-imports the module from scratch,
# so these start as ``None``; under ``fork`` (Linux) they are inherited from the
# parent, which also leaves them ``None``. Either way only the initializer sets
# them, and the parent process never does — the module is import-safe.
_worker_static = None
_worker_static_affine = None


def _pool_context(platform=None):
    """Return the multiprocessing start-method context for this platform.

    User decision (2026-09-05), superseding the earlier spawn-everywhere choice:

    * **Linux → fork** — workers inherit the parent, so dipy is not re-imported
      per worker; this is the fastest start method and avoids the ~33% wall-clock
      penalty spawn pays on this path.
    * **Windows → spawn** — fork is unavailable on Windows.
    * **macOS → spawn** — fork is unsafe on macOS (Python's own default is spawn
      since 3.8 because the system frameworks, Accelerate/Objective-C included,
      are not fork-safe), and there is no macOS box to validate a faster
      ``forkserver``, so spawn is the safe, tested choice.

    This platform-conditional choice is safe because BLAS is pinned in the pool
    ``initializer`` (and ``threadpool_limits(1)`` wraps each registration), never
    via parent-environment inheritance. The initializer runs under every start
    method, so no worker is ever left unpinned — which defuses the
    fork-inherits/spawn-doesn't trap that had motivated the earlier uniform-spawn
    decision.
    """
    platform = platform or sys.platform
    if platform.startswith("linux"):
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context("spawn")


def _worker_initializer(blas_threads, static=None, static_affine=None):
    """Pool initializer: pin BLAS threads and hoist the static reference.

    Under ``spawn`` each worker re-imports the module and starts from library
    defaults, so a pin applied at import in the parent is silently lost; under
    ``fork`` a worker would inherit whatever the parent had set (``num_threads``,
    not 1). Pinning here — in the initializer, which runs under every start
    method — is therefore the one placement correct on all platforms.

    Parameters
    ----------
    blas_threads : int
        Number of BLAS threads per worker (1 for the parallel path, so each
        worker is single-threaded and the footprint stays at ``n_procs × 1``).
    static : ndarray or None
        The 3D static reference volume, shared by every job. Hoisted here so
        it travels once per worker (via ``initargs``) instead of once per
        volume in the per-job payload.
    static_affine : ndarray or None
        The 4×4 affine for the static reference.
    """
    global _worker_static, _worker_static_affine
    threads_str = str(max(1, int(blas_threads)))
    os.environ[OMP_THREADS_VAR] = threads_str
    os.environ[OPENBLAS_THREADS_VAR] = threads_str
    if static is not None:
        _worker_static = static
    if static_affine is not None:
        _worker_static_affine = static_affine


def _register_one_volume(index, moving, moving_affine, pipeline):
    """Register one moving volume to the static reference (BLAS pinned to 1).

    Returns ``(index, transformed_volume, reg_affine)``. The index travels with
    the payload so the driver can reassemble results by volume position no
    matter what order the workers finish in.

    The static reference and its affine are read from the module-level globals
    ``_worker_static`` and ``_worker_static_affine``, set by
    ``_worker_initializer`` in each worker. This avoids pickling and shipping the
    (identical) static volume with every single job (a real saving under spawn,
    where every payload is pickled; free under fork, where it is inherited).
    """
    with threadpool_limits(limits=1):
        transformed, reg_affine = affine_registration(
            moving,
            _worker_static,
            moving_affine=moving_affine,
            static_affine=_worker_static_affine,
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

    The start method is chosen per platform by ``_pool_context`` (fork on Linux,
    spawn on Windows/macOS; user decision 2026-09-05). The pool is built **once**
    with ``_worker_initializer`` as the initializer: it pins
    ``OMP_NUM_THREADS``/``OPENBLAS_NUM_THREADS`` to 1 in each worker — required on
    every start method, since spawn inherits no environment pins and fork would
    otherwise inherit the parent's ``num_threads`` — and hoists the static
    reference into a module-level global so it travels once per worker instead of
    once per volume. Building the pool once matters most under spawn, where each
    worker re-imports dipy (seconds); under fork there is no re-import, so it is
    simply harmless.
    """
    register_fn = register_fn or _register_one_volume
    n_vols = moving_data.shape[-1]
    # Volume buffer float32 (C2.3): it holds the full stack of resampled 3D
    # volumes and is the node's memory ceiling, so halving its dtype halves that
    # RAM. The affine buffer stays float64 — it is 4x4 per volume (negligible
    # memory) and its precision propagates to every voxel.
    xformed = np.zeros(moving_data.shape, dtype=np.float32)
    affines = np.zeros((4, 4, n_vols))

    max_workers = max(1, int(num_threads))

    if use_processes:
        # fork on Linux, spawn on Windows/macOS (user decision 2026-09-05)
        ctx = _pool_context()
        executor_cls = ProcessPoolExecutor
        executor_kwargs = dict(
            max_workers=max_workers,
            mp_context=ctx,
            initializer=_worker_initializer,
            initargs=(1, static, affine),
        )
    else:
        # Thread pool for the reassembly unit test (no spawn overhead).
        executor_cls = ThreadPoolExecutor
        executor_kwargs = dict(max_workers=max_workers)
        # For the thread path, set the module globals directly so
        # _register_one_volume can read them.
        global _worker_static, _worker_static_affine
        _worker_static = static
        _worker_static_affine = affine

    with executor_cls(**executor_kwargs) as executor:
        futures = [
            executor.submit(
                register_fn,
                index,
                moving_data[..., index],
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

    # Affine array stays float64 (see _register_moving_volumes); the assembled
    # volume buffer is float32 (C2.3) — the transformed b0s and moving volumes
    # are downcast on assignment into it.
    affine_array = np.zeros((4, 4, data.shape[-1]))
    affine_array[..., b0s_mask] = b0_affines
    affine_array[..., ~b0s_mask] = moving_affines

    data_array = np.zeros(data.shape, dtype=np.float32)
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

        # Save the motion-corrected 4D image as float32. The registered volumes
        # are a float computation; casting them back to the raw dcm2niix DWI's
        # int16 on-disk dtype (inherited via ``img.header``) would quantize every
        # correction. Reading the data at float32 keeps the serial reference and
        # the parallel path bit-for-bit equal -- the
        # parallel path already assembles into a float32 buffer -- and writing
        # float32 on disk makes that correction lossless. The affine/orientation/
        # zooms from the source header are preserved; only the data dtype changes.
        out_img = nib.Nifti1Image(
            registered_img.get_fdata(dtype=np.float32),
            img.affine,
            img.header,
        )
        out_img.header.set_data_dtype(np.float32)
        nib.save(out_img, self._gen_outfilename("out_file", "moco_"))

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
