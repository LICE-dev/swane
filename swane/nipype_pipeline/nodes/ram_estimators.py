# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import math

import numpy as np
import nibabel as nib
from nipype.interfaces.base import isdefined
from nipype.utils.ram_estimator import RamEstimator

from swane.utils.ResourceManager import ResourceManager


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class FlirtRamEstimator(RamEstimator):
    """
    RAM estimator for FSL FLIRT with calibrated multipliers and overhead.
    """

    def __init__(self):
        # Set FLIRT-specific parameters
        super().__init__(
            input_multipliers={
                "in_file": 12,  # main input
                "reference": 2,  # reference
            },
            overhead_gb=0.30,
            min_gb=0.3,
            max_gb=4.0,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class FnirtRamEstimator(RamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """

    def __init__(self):
        super().__init__(
            input_multipliers={
                "in_file": 24,  # contributes, but secondary
                "ref_file": 200,  # warp field + gradients + pyramid
            },
            overhead_gb=1.8,  # control structures + buffers
            min_gb=2,  # FNIRT is never really small
            max_gb=8.0,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class InvWarpRamEstimator(RamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """

    def __init__(self):
        super().__init__(
            input_multipliers={
                "warp": 2,  # contributes, but secondary
                "reference": 48,  # warp field + gradients + pyramid
            },
            overhead_gb=0.3,
            min_gb=0.4,
            max_gb=6.0,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class FastRamEstimator(RamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """

    def __init__(self):
        super().__init__(
            input_multipliers={
                "in_files": 110,  # contributes, but secondary
            },
            overhead_gb=0.3,
            min_gb=1,
            max_gb=8,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipyCropRamEstimator(RamEstimator):
    """
    RAM estimator for :class:`DwiCrop` -- one-way, no quality-neutral lever.

    Model
    -----
    The node loads the whole 4D series as float32 and holds it alongside the
    mean-volume mask and the cropped copy, so the peak tracks the input's
    voxel x volume count, the same regressor family as
    :class:`DipyMotionRamEstimator`/:class:`DipyCsdRamEstimator`::

        mem_gb = OVERHEAD_GB + BYTES_PER_VOXEL_VOLUME * voxels * volumes / 2**30

    ``median_otsu``'s thread count is not a lever here (numpy/scipy single-
    threaded work; ``num_threads`` only pins the OMP/OpenBLAS env vars), so
    this estimator is one-way like :class:`DipyTissueRamEstimator`.

    Calibration
    -----------
    Isolated tree-peak RSS on three real subject DWIs (voxel x volume,
    measured GB): 54.5M -> 0.53, 80.9M -> 1.15, 167.7M -> 2.43. A least-
    squares fit gives ~17.4 B/(voxel x volume); the constant below rounds
    that up to 20, covering every measured point with a 1.4-2.5x margin.
    """

    #: Bytes per (voxel x volume) of the 4D series. Fit ~17.4 B, rounded up.
    BYTES_PER_VOXEL_VOLUME = 20

    #: Fixed overhead (interpreter, numpy/dipy/nibabel).
    OVERHEAD_GB = 0.3

    #: No crop fits in less than this, whatever the input.
    MIN_GB = 0.5

    #: Static reservation the workflow declares on the node. Read only when
    #: the negotiation cannot run at all (see
    #: ``MonitoredMultiProcPlugin._negotiate_ram``). A conservative
    #: representative peak, rounded up from the largest measured subject.
    STATIC_FALLBACK_GB = 3.5

    def __init__(self):
        super().__init__(
            input_multipliers={},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )

    @staticmethod
    def _shape(inputs):
        """Return ``(spatial_voxels, volumes)`` from the input header alone."""
        img = nib.load(inputs.in_file)
        shape = img.header.get_data_shape()
        voxels = int(math.prod(shape[:3]))
        volumes = int(shape[3]) if len(shape) > 3 else 1
        return voxels, volumes

    def estimate_gb(self, voxels, volumes):
        total = (
            self.OVERHEAD_GB + self.BYTES_PER_VOXEL_VOLUME * voxels * volumes / 1024**3
        )
        return float(self.clamp(total, self.min_gb, None))

    def __call__(self, inputs):
        voxels, volumes = self._shape(inputs)
        mem_gb = self.estimate_gb(voxels, volumes)
        return mem_gb, (
            "voxels=%d, volumes=%d, estimated RAM=%.2f GB" % (voxels, volumes, mem_gb)
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipyMotionRamEstimator(RamEstimator):
    """
    Tunable RAM estimator for :class:`DipyMotionCorrection`, with the pool
    worker count as its quality-neutral lever.

    Model
    -----
    The driver process holds the whole 4D series -- the float64 array read from
    disk, the ``moving_data`` copy, the float32 output buffers and the save-time
    copy -- so its peak tracks ``voxels * volumes``::

        parent_gb = OVERHEAD_GB + PARENT_BYTES_PER_VOXEL_VOLUME * V * T / 2**30

    Each pool worker then adds a roughly **fixed fraction of that parent peak**,
    not a share proportional to the volume it is registering::

        mem_gb = parent_gb * (1 + WORKER_PARENT_SHARE * workers)

    That second term is measured, not assumed. On Linux the pool uses ``fork``,
    so every child's RSS also counts the copy-on-write pages it inherits from
    the parent; what the scheduler must budget for is therefore driven by the
    parent's resident set rather than by the size of a single 3D volume. Across
    11 isolated runs spanning V = 0.16-3.41 Mvoxel, T = 8-65 volumes and W = 1-4
    workers, the per-worker contribution stayed at 0.58-0.87 of the parent peak
    and showed no usable correlation with V alone (it is *anti*-correlated: 388
    B/voxel at V=3.41M against 1233 B/voxel at V=1.24M).

    Tuning
    ------
    Halving the worker count is quality-neutral: BLAS is pinned to a single
    thread inside every worker whatever their number, and results are
    reassembled strictly by volume index, so the corrected series and the
    reoriented gradients are bit-for-bit identical at any rung -- only wall time
    changes. ``negotiate`` therefore returns the largest ``num_threads`` whose
    estimate fits the RAM budget, capped by the value the workflow declared.

    Calibration
    -----------
    Per the RAM design's estimation philosophy these constants are a deliberate
    **over-estimate**, not a fitted curve. The least-squares fit over the 11 runs
    gives 26-28 B per voxel-volume, a 0.21-0.36 GB constant and a 0.87 maximum
    worker share; the values below are rounded up from those, which keeps every
    measured point covered by 1.21x-1.86x. Two further margins sit on top: the
    measurement itself sums per-process RSS, which double-counts fork's shared
    pages and so over-states real physical use; and on the spawn path
    (macOS/Windows) each worker is private and smaller than the fork-calibrated
    share.
    """

    #: Parent-side bytes per (voxel x volume). Fit: 26-28 B, rounded up.
    PARENT_BYTES_PER_VOXEL_VOLUME = 32

    #: Fixed parent overhead (interpreter, numpy/dipy/nibabel). Fit: 0.21-0.36 GB.
    OVERHEAD_GB = 0.30

    #: Per-worker share of the parent peak. Measured range 0.58-0.87.
    WORKER_PARENT_SHARE = 0.9

    #: Static reservation the workflow declares on the node. It is only read
    #: when the negotiation cannot run at all (see
    #: ``MonitoredMultiProcPlugin._negotiate_ram``), which for this estimator
    #: means the input header could not be read -- a state in which the node
    #: itself cannot run either. It holds the ladder's bottom rung for a
    #: representative DWI (about 2 Mvoxel x 32 volumes); the dipy engine's RAM
    #: floor is settled jointly at the end of Phase 2 and may revise it.
    STATIC_FALLBACK_GB = 4.5

    #: No registration fits in less than this, whatever the input.
    MIN_GB = 0.5

    def __init__(self):
        # max_gb is deliberately None: clamping the estimate down would make the
        # node under-reserve and silently co-schedule with other heavy work,
        # which is the exact failure this estimator exists to prevent. Deciding
        # that a node cannot fit is the scheduler's job, not the estimator's.
        super().__init__(
            input_multipliers={},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )

    @staticmethod
    def _shape(inputs):
        """Return ``(spatial_voxels, volumes)`` from the input header alone."""
        img = nib.load(inputs.in_file)
        shape = img.header.get_data_shape()
        voxels = int(math.prod(shape[:3]))
        volumes = int(shape[3]) if len(shape) > 3 else 1
        return voxels, volumes

    @staticmethod
    def _declared_workers(inputs):
        """The pool size the workflow asked for (the ladder's top rung).

        The serial path (``parallel=False``) runs the registrations in the
        driver process itself, so it is priced as a single worker and has no
        lever to walk.
        """
        if not getattr(inputs, "parallel", True):
            return 1
        if isdefined(getattr(inputs, "num_threads", None)):
            return max(1, int(inputs.num_threads))
        return 1

    def parent_gb(self, voxels, volumes):
        """The driver process's peak: the whole 4D series plus a constant."""
        per_voxel_volume = self.PARENT_BYTES_PER_VOXEL_VOLUME / 1024**3
        return self.OVERHEAD_GB + voxels * volumes * per_voxel_volume

    def estimate_gb(self, voxels, volumes, workers):
        """Parent peak plus each worker's share of it."""
        total = self.parent_gb(voxels, volumes) * (
            1 + self.WORKER_PARENT_SHARE * max(1, int(workers))
        )
        return float(self.clamp(total, self.min_gb, None))

    def bottom_rung_gb(self, voxels, volumes):
        """The estimate at the bottom of the ladder (a single pool worker)."""
        return self.estimate_gb(voxels, volumes, 1)

    def max_workers_for_budget(self, voxels, volumes, ram_budget_gb, declared):
        """The largest worker count whose estimate fits ``ram_budget_gb``.

        The model is monotone in ``W``, so the rung is closed-form rather than a
        search::

            parent * (1 + share * W) <= budget
            W <= (budget / parent - 1) / share

        A coarser ladder would leave budget unspent: halving from 10 workers
        (10 -> 5 -> 2 -> 1) picks 2 on a budget where 3 fit, discarding a third
        of the throughput for no technical reason. The result is clamped to
        ``[1, declared]`` -- the workflow's ``num_threads`` is a cap the
        estimator must never raise -- and the two guard loops absorb any
        floating-point edge so the returned rung is exactly the largest one that
        fits.
        """
        parent = self.parent_gb(voxels, volumes)
        declared = max(1, int(declared))
        if parent <= 0:  # pragma: no cover - defensive, parent >= OVERHEAD_GB
            return declared

        workers = math.floor((ram_budget_gb / parent - 1) / self.WORKER_PARENT_SHARE)
        workers = max(1, min(declared, int(workers)))
        while (
            workers > 1 and self.estimate_gb(voxels, volumes, workers) > ram_budget_gb
        ):
            workers -= 1
        while (
            workers < declared
            and self.estimate_gb(voxels, volumes, workers + 1) <= ram_budget_gb
        ):
            workers += 1
        return workers

    def __call__(self, inputs):
        """One-way estimate at the declared (untuned) worker count."""
        voxels, volumes = self._shape(inputs)
        workers = self._declared_workers(inputs)
        mem_gb = self.estimate_gb(voxels, volumes, workers)
        return mem_gb, (
            "voxels=%d, volumes=%d, workers=%d (untuned), parent=%.2f GB, "
            "estimated RAM=%.2f GB"
            % (voxels, volumes, workers, self.parent_gb(voxels, volumes), mem_gb)
        )

    def negotiate(self, inputs, ram_budget_gb):
        """Reserve RAM and tune the worker count to the budget.

        Returns the largest worker count that fits. When even a single worker
        exceeds the budget the bottom rung is returned anyway, and said so in
        the debug trace: the generation-time RAM gate is what guarantees a
        permitted host can run the bottom rung, so refusing here would turn a
        tight fit into a dead workflow instead of a slow one.
        """
        from swane.patches.nipype_patches import RamPlan

        voxels, volumes = self._shape(inputs)
        declared = self._declared_workers(inputs)

        chosen = self.max_workers_for_budget(voxels, volumes, ram_budget_gb, declared)
        mem_gb = self.estimate_gb(voxels, volumes, chosen)
        exhausted = mem_gb > ram_budget_gb

        debug = (
            "voxels=%d, volumes=%d, parent=%.2f GB, workers %d -> %d, "
            "budget=%.2f GB, estimated RAM=%.2f GB"
            % (
                voxels,
                volumes,
                self.parent_gb(voxels, volumes),
                declared,
                chosen,
                ram_budget_gb,
                mem_gb,
            )
        )
        if exhausted:
            debug += " (ladder exhausted: bottom rung still exceeds the budget)"

        return RamPlan(
            mem_gb=mem_gb,
            tuned_params={"num_threads": chosen},
            n_procs=chosen,
            debug_str=debug,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipyTrackingRamEstimator(RamEstimator):
    """
    Tunable RAM estimator for :class:`DipyTracking`, with two quality-neutral
    levers walked at scheduling time to fit the RAM budget.

    Model
    -----
    After the Phase-1bis brain-bbox crop, float32 SH load and streaming ``.trx``
    fixes, tracking's peak has three terms::

        parent_gb = OVERHEAD_GB + VOXEL_BYTES * brain_voxels / 2**30
        seed_gb   = SEED_BYTES  * seeds * buffer_fraction / 2**30
        trx_gb    = TRX_BYTES   * chunk_size / 2**30
        mem_gb    = parent_gb + seed_gb + trx_gb

    ``brain_voxels`` is the count the node actually works on: the ``nodif_brain``
    foreground bounding box (the same crop the node applies), **not** the full
    ``shm_coeff`` FOV. Because the node crops to the brain internally, the peak
    tracks the cropped-brain voxel count; pricing the full FOV would both
    over-reserve when the FOV carries wide background margins and *under*-reserve
    when a tight FOV still holds the whole brain. ``seeds`` is the seed count the node
    places -- ``seed_density`` per ``REFERENCE_VOXEL_MM3`` of the ``pve_wm``
    mask's volume -- which is what the buffer lever scales.

    Tuning
    ------
    Two levers, walked in order:

    * ``seed_buffer_fraction`` -- the fraction of the seed pool
      ``probabilistic_tracking`` buffers per streaming chunk. Superseding the
      node's hardcoded 0.7, ``negotiate`` returns the **largest** fraction in
      ``[BUFFER_MIN, BUFFER_MAX]`` that fits the budget: up to dipy's 1.0 when
      budget is ample, down to 0.3 under pressure.
    * ``trx_chunk_size`` -- the ``.trx`` write chunk, walked down toward
      ``CHUNK_MIN`` only **after** the buffer floor is reached (its RAM
      contribution is small; streaming already keeps the write peak flat).

    Both levers are bit-for-bit quality-neutral: seeds are consumed in a fixed
    order and each streamline's trajectory is a pure function of its seed
    coordinate and ``random_seed``, so the tractogram is identical at any rung --
    only wall time / peak RSS change (proven by the tuned-vs-untuned heavy test).
    ``seed_buffer_fraction`` is the dominant lever and genuinely earns its place.
    Threads are **not** a lever here (that is the CSD/tissue estimators' job), so
    the plan's ``n_procs`` is left None and the CPU reservation is unchanged.

    Calibration
    -----------
    Per the RAM design's estimation philosophy these constants are a deliberate
    **coarse over-estimate**, not a fitted curve: the estimator's job is to reserve
    enough and keep the heavy nodes apart, not to account for RAM to the megabyte.
    Each rung's bound stays conservative (estimate >= real peak) with margin; when
    in doubt the constants round up.
    """

    #: Parent bytes per *brain* voxel (nodif_brain bbox, not full FOV): SH working
    #: set + tracker buffers + transient load. Conservative bound, not a fit.
    VOXEL_BYTES = 2255

    #: Per buffered-seed working set -- the dominant lever. Conservative bound,
    #: rounded up.
    SEED_BYTES = 11000

    #: Per-streamline ``.trx`` write-chunk bytes (the smaller, secondary lever).
    TRX_BYTES = 4096

    #: Fixed parent overhead (interpreter, numpy/dipy/trx/nibabel).
    OVERHEAD_GB = 0.5

    #: Buffer-fraction ladder bounds. Top supersedes the node's hardcoded 0.7 up to
    #: dipy's 1.0; bottom is the streaming floor (user decision, 2026-09-06).
    BUFFER_MAX = 1.0
    BUFFER_MIN = 0.3

    #: The ``.trx`` chunk floor the secondary lever walks down to.
    CHUNK_MIN = 1000

    #: No tracking run fits in less than this, whatever the input.
    MIN_GB = 0.5

    #: Static reservation the workflow declares on the node. Read only when the
    #: negotiation cannot run at all (see ``MonitoredMultiProcPlugin._negotiate_ram``)
    #: -- e.g. an input could not be read, a state in which the node cannot run
    #: either. A conservative representative top-rung value; the dipy engine's RAM
    #: floor is settled jointly at the end of Phase 2 and may revise it.
    STATIC_FALLBACK_GB = 7.5

    def __init__(self):
        # max_gb is deliberately None: clamping the estimate down would make the
        # node under-reserve and silently co-schedule with other heavy work.
        # Deciding a node cannot fit is the scheduler's job, not the estimator's.
        super().__init__(
            input_multipliers={},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )

    @staticmethod
    def _brain_voxels(inputs):
        """Voxel count the node actually holds: the ``nodif_brain`` foreground
        bounding box (the same crop :class:`DipyTracking` applies), not the full
        ``shm_coeff`` FOV -- this is what the peak tracks."""
        from swane.nipype_pipeline.nodes.DipyTracking import foreground_bbox_slices

        nodif = np.asarray(nib.load(inputs.nodif_brain).dataobj)
        slices = foreground_bbox_slices((nodif,), nodif.shape[:3])
        return int(math.prod(s.stop - s.start for s in slices))

    @staticmethod
    def _seed_count(inputs):
        """The seed pool the buffer lever scales, from the same volume density
        the node seeds at. Reads the mask, never the SH data."""
        from swane.nipype_pipeline.nodes.DipyTracking import (
            seed_count_for_volume,
            wm_seed_mask,
        )

        density = int(inputs.seed_density) if isdefined(inputs.seed_density) else 2
        pve_nii = nib.load(inputs.pve_wm)
        mask = wm_seed_mask(pve_nii.get_fdata())
        return seed_count_for_volume(mask, pve_nii.affine, density)

    @staticmethod
    def _declared_chunk(inputs):
        """The ``.trx`` chunk the workflow declared -- the ladder's chunk cap."""
        if isdefined(getattr(inputs, "trx_chunk_size", None)):
            return int(inputs.trx_chunk_size)
        return 10000

    def parent_gb(self, voxels):
        """The incompressible brain working set plus a constant (``voxels`` is the
        cropped-brain count from :meth:`_brain_voxels`)."""
        return self.OVERHEAD_GB + self.VOXEL_BYTES * voxels / 1024**3

    def seed_gb(self, seeds, buffer):
        return self.SEED_BYTES * seeds * buffer / 1024**3

    def trx_gb(self, chunk):
        return self.TRX_BYTES * chunk / 1024**3

    def estimate_gb(self, voxels, seeds, buffer, chunk):
        total = (
            self.parent_gb(voxels) + self.seed_gb(seeds, buffer) + self.trx_gb(chunk)
        )
        return float(self.clamp(total, self.min_gb, None))

    def bottom_rung_gb(self, voxels, seeds):
        """The estimate at the bottom of the ladder (min buffer, min chunk)."""
        return self.estimate_gb(voxels, seeds, self.BUFFER_MIN, self.CHUNK_MIN)

    def max_buffer_for_budget(self, voxels, seeds, ram_budget_gb, chunk):
        """The largest buffer fraction whose estimate fits, at a fixed chunk.

        Closed form (the model is linear in the fraction)::

            parent + trx + seed_unit * buffer <= budget
            buffer <= (budget - parent - trx) / seed_unit

        Clamped to ``[BUFFER_MIN, BUFFER_MAX]`` -- the estimator supersedes the
        node's declared fraction up to dipy's 1.0 but never below the streaming
        floor.
        """
        fixed = self.parent_gb(voxels) + self.trx_gb(chunk)
        seed_unit = self.SEED_BYTES * seeds / 1024**3
        if seed_unit <= 0:
            return self.BUFFER_MAX
        buffer = (ram_budget_gb - fixed) / seed_unit
        return float(min(self.BUFFER_MAX, max(self.BUFFER_MIN, buffer)))

    def max_chunk_for_budget(
        self, voxels, seeds, ram_budget_gb, buffer, declared_chunk
    ):
        """The largest chunk whose estimate fits, at a fixed (floor) buffer.

        Closed form (linear in the chunk); clamped to ``[CHUNK_MIN,
        declared_chunk]`` -- the workflow's chunk is a cap the estimator never
        raises.
        """
        base = self.parent_gb(voxels) + self.seed_gb(seeds, buffer)
        trx_unit = self.TRX_BYTES / 1024**3
        chunk = math.floor((ram_budget_gb - base) / trx_unit)
        return int(min(int(declared_chunk), max(self.CHUNK_MIN, chunk)))

    def __call__(self, inputs):
        """One-way estimate at the top rung (max buffer, declared chunk)."""
        voxels = self._brain_voxels(inputs)
        seeds = self._seed_count(inputs)
        chunk = self._declared_chunk(inputs)
        mem_gb = self.estimate_gb(voxels, seeds, self.BUFFER_MAX, chunk)
        return mem_gb, (
            "voxels=%d, seeds=%d, buffer=%.2f (untuned), chunk=%d, "
            "parent=%.2f GB, estimated RAM=%.2f GB"
            % (voxels, seeds, self.BUFFER_MAX, chunk, self.parent_gb(voxels), mem_gb)
        )

    def negotiate(self, inputs, ram_budget_gb):
        """Reserve RAM and tune the two levers to the budget.

        Walks ``seed_buffer_fraction`` down first (the larger lever), then, only
        if the buffer floor still exceeds the budget, ``trx_chunk_size``. When
        even the bottom rung exceeds the budget it is returned anyway and said so
        in the trace: the generation-time RAM gate is what guarantees a permitted
        host can run the bottom rung, so refusing here would turn a tight fit into
        a dead workflow instead of a slow one.
        """
        from swane.patches.nipype_patches import RamPlan

        voxels = self._brain_voxels(inputs)
        seeds = self._seed_count(inputs)
        declared_chunk = self._declared_chunk(inputs)

        buffer = self.max_buffer_for_budget(
            voxels, seeds, ram_budget_gb, declared_chunk
        )
        chunk = declared_chunk
        mem_gb = self.estimate_gb(voxels, seeds, buffer, chunk)

        if mem_gb > ram_budget_gb and buffer <= self.BUFFER_MIN:
            buffer = self.BUFFER_MIN
            chunk = self.max_chunk_for_budget(
                voxels, seeds, ram_budget_gb, buffer, declared_chunk
            )
            mem_gb = self.estimate_gb(voxels, seeds, buffer, chunk)

        exhausted = mem_gb > ram_budget_gb

        debug = (
            "voxels=%d, seeds=%d, parent=%.2f GB, buffer -> %.3f, chunk %d -> %d, "
            "budget=%.2f GB, estimated RAM=%.2f GB"
            % (
                voxels,
                seeds,
                self.parent_gb(voxels),
                buffer,
                declared_chunk,
                chunk,
                ram_budget_gb,
                mem_gb,
            )
        )
        if exhausted:
            debug += " (ladder exhausted: bottom rung still exceeds the budget)"

        return RamPlan(
            mem_gb=mem_gb,
            tuned_params={
                "seed_buffer_fraction": buffer,
                "trx_chunk_size": int(chunk),
            },
            n_procs=None,
            debug_str=debug,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipyTissueRamEstimator(RamEstimator):
    """
    RAM estimator for :class:`DipyTissueClassifier` -- deliberately **classic**
    (one-way), not tunable.

    Why one-way
    -----------
    Unlike motion, tracking and CSD, this node has no quality-neutral lever to
    walk. It runs dipy's ``TissueClassifierHMRF.classify`` on the T1
    ``reference_brain`` and already pins ``OMP_NUM_THREADS=1`` inside
    ``classify`` (see :class:`DipyTissueClassifier`); it exposes no thread or
    worker trait. Peak RSS is **byte-identical across threads** and
    wall time is flat too: the HMRF classify is a serial Python/numpy loop that
    OMP/BLAS threads do not parallelise. A thread lever would tune nothing, so
    this estimator inherits the default :meth:`negotiate` (empty ``tuned_params``,
    ``n_procs=None``): it reserves RAM and applies no bidirectional correction.

    Model
    -----
    The same probes showed peak RSS is **linear in the input voxel count**. The
    HMRF holds the T1 (float64) plus its per-iteration working arrays (the
    segmented image and the ``voxels x nclasses`` PVE/energy buffers), all
    allocated up front, so the peak tracks spatial voxels alone::

        mem_gb = OVERHEAD_GB + BYTES_PER_VOXEL * voxels / 2**30

    computed by the base :meth:`RamEstimator.__call__` from
    ``input_multipliers={"in_file": BYTES_PER_VOXEL}``.

    Parameters
    ----------
    Per the RAM design's estimation philosophy the constants are a deliberate
    conservative **over-estimate**, not a fitted curve, providing safe margin
    across input dimensions.
    """

    #: Bytes per spatial voxel of the T1 ``in_file``. Fit ~260 B, rounded up.
    BYTES_PER_VOXEL = 280

    #: Fixed overhead (interpreter, numpy/dipy/nibabel). Fit ~0.36 GB, rounded up.
    OVERHEAD_GB = 0.4

    #: No classification fits in less than this, whatever the input.
    MIN_GB = 0.5

    #: Static reservation the workflow declares on the node. Read only when the
    #: negotiation cannot run at all (see
    #: ``MonitoredMultiProcPlugin._negotiate_ram``) -- e.g. the input header could
    #: not be read, a state in which the node itself cannot run. A conservative
    #: representative peak with margin. This node has no
    #: lever (unlike motion/tracking/CSD), but it is no longer the dipy engine's
    #: binding floor -- real-tractogram measurement showed DipyAtlasSLR's own
    #: no-lever floor is higher (see DipySlrRamEstimator), so
    #: ResourceManager.DIPY_TRACTOGRAPHY_RAM_REQUIREMENT is sourced from SLR now.
    STATIC_FALLBACK_GB = 6.0

    def __init__(self):
        # max_gb is deliberately None: clamping the estimate down would make the
        # node under-reserve and silently co-schedule with other heavy work,
        # which is the exact failure this estimator exists to prevent. Deciding
        # that a node cannot fit is the scheduler's job, not the estimator's.
        super().__init__(
            input_multipliers={"in_file": self.BYTES_PER_VOXEL},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipyCsdRamEstimator(RamEstimator):
    """
    Tunable RAM estimator for :class:`DipyCsdFit`, with the
    ``peaks_from_model`` worker count as its quality-neutral lever.

    Two regimes, not one curve
    --------------------------
    dipy's ``peaks_from_model`` has two structurally different branches, and the
    estimator models them separately because their memory profiles differ in
    kind, not degree:

    * **Serial** (``num_processes == 1``) allocates a single full-volume set of
      output arrays: ``gfa``, ``qa``, ``peak_dirs``, ``peak_values``,
      ``peak_indices`` and ``shm_coeff``.
    * **Parallel** (``num_processes > 1``) splits the series into ``P**2``
      chunks and holds **three** full-volume equivalents at once: every chunk
      result returned by ``pool.map`` is alive in the parent simultaneously,
      each is copied into an ``np.memmap``, and those are read back with
      ``np.array``. That triple is independent of ``P``.
    * Each of the ``P`` concurrent workers additionally holds its own chunk's
      arrays (``voxels / P**2`` each), so the aggregate worker term is
      ``voxels / P`` -- it *shrinks* as ``P`` grows -- plus one ``spawn``
      interpreter per worker (dipy forces the spawn start method here, so a
      worker is a fresh interpreter with numpy/dipy imported, not a fork).

    So::

        per_voxel = PEAK_BYTES_PER_VOXEL + SH_BYTES_PER_COEFF * n_coeff
        data_gb   = DATA_BYTES_PER_VOXEL_VOLUME * voxels * volumes / 2**30

        serial   = OVERHEAD + data_gb + SERIAL_COPIES   * per_voxel * voxels
        parallel = OVERHEAD + data_gb + PARALLEL_COPIES * per_voxel * voxels
                                      + per_voxel * voxels / P
                                      + P * SPAWN_GB_PER_WORKER

    The voxel count of the input sequence is therefore the primary regressor --
    it drives both the 4D buffer (with the volume count) and every per-voxel
    output array -- and the SH coefficient count is the secondary one, itself
    derived from the acquisition's direction count.

    Why the ladder scans instead of halving
    ---------------------------------------
    The consequence of the above is that RAM **need not be monotone in P**:
    inside the parallel branch the parent term is constant while the worker term
    falls as ``1/P`` and the spawn term grows linearly, so above a volume
    threshold 4 -> 2 *raises* the estimate. A halving ladder
    would therefore not be guaranteed to converge downwards. The real cliff is
    ``P == 1``, which switches to the serial branch and drops two of the three
    full-volume copies. :meth:`negotiate` evaluates every rung from the declared
    count down to 1 and returns the largest one that fits, with the serial rung
    as the floor.

    Tuning
    ------
    Lowering the worker count is quality-neutral: dipy chunks strictly by voxel
    index and reassembles by the same index, each worker runs the identical
    serial per-voxel fit, and BLAS is pinned to one thread per worker whatever
    their number (:class:`DipyCsdFit` sets ``OMP_NUM_THREADS`` before the pool
    starts, and spawn workers inherit the environment). The written
    ``shm_coeff`` is therefore bit-for-bit identical at any rung -- only wall
    time changes. (dipy's ``qa`` array is *not* rung-invariant, because each
    chunk normalises by its own ``global_max``; the node does not save it.)

    Parameters
    ----------
    Per the RAM design's estimation philosophy these constants are a deliberate
    **over-estimate**, not a fitted curve. ``PEAK_BYTES_PER_VOXEL`` and
    ``SH_BYTES_PER_COEFF`` are read off the dipy allocations exactly
    (``npeaks=1`` as the node pins it: ``gfa`` 8 + ``qa`` 8 + ``peak_dirs`` 24 +
    ``peak_values`` 8 + ``peak_indices`` 4 = 52 B, plus 8 B per SH coefficient),
    and the copy multiplicities are counted from the dipy source.
    """

    #: Bytes per (voxel x volume) for the 4D series. The node now loads the DWI
    #: as **float32** (``get_fdata(dtype=np.float32)``, user decision 2026-09-07),
    #: so the input buffer is 4 B/element resident (was 8 B under the old float64
    #: get_fdata) plus a same-size raw copy during the load: 4 (resident at the
    #: peaks_from_model peak) up to 4 + 4 = 8 (load transient) B, rounded to 8.
    #: This *supersedes* the interim int16->float32 value (10 -> 12) that assumed
    #: a float64 load; the float32 load lowers the real data term, so 8 is both
    #: accurate and conservative. The dominant term is the per-voxel output-array
    #: copies (float64 SH, unchanged), so the estimate stays conservative at
    #: both the serial and the 4-worker rungs.
    DATA_BYTES_PER_VOXEL_VOLUME = 8

    #: Per-voxel bytes of the non-SH output arrays at the node's pinned
    #: ``npeaks=1``: gfa 8 + qa 8 + peak_dirs 24 + peak_values 8 +
    #: peak_indices 4. Read off the dipy allocations, not fitted.
    PEAK_BYTES_PER_VOXEL = 52

    #: Bytes per SH coefficient per voxel (``shm_coeff`` is float64).
    SH_BYTES_PER_COEFF = 8

    #: Full-volume copies alive at once on the serial branch.
    SERIAL_COPIES = 1

    #: Full-volume copies alive at once on the parallel branch: the pooled
    #: chunk results, the memmaps they are written into, and the arrays they
    #: are read back as.
    PARALLEL_COPIES = 3

    #: A spawned worker is a fresh interpreter with numpy/dipy imported.
    SPAWN_GB_PER_WORKER = 0.25

    #: Fixed parent overhead (interpreter, numpy/dipy/nibabel).
    OVERHEAD_GB = 0.4

    #: No CSD fit fits in less than this, whatever the input.
    MIN_GB = 0.5

    #: Static reservation the workflow declares on the node. It is only read
    #: when the negotiation cannot run at all (see
    #: ``MonitoredMultiProcPlugin._negotiate_ram``), which for this estimator
    #: means the input header or the bval file could not be read -- a state in
    #: which the node itself cannot run either. It holds the estimate at the
    #: declared rung for a representative DWI (about 3.7 GB), rounded up.
    STATIC_FALLBACK_GB = 4.0

    def __init__(self):
        # max_gb is deliberately None: clamping the estimate down would make the
        # node under-reserve and silently co-schedule with other heavy work,
        # which is the exact failure this estimator exists to prevent. Deciding
        # that a node cannot fit is the scheduler's job, not the estimator's.
        super().__init__(
            input_multipliers={},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )

    @staticmethod
    def _shape(inputs):
        """Return ``(spatial_voxels, volumes)`` from the input header alone."""
        img = nib.load(inputs.in_file)
        shape = img.header.get_data_shape()
        voxels = int(math.prod(shape[:3]))
        volumes = int(shape[3]) if len(shape) > 3 else 1
        return voxels, volumes

    @staticmethod
    def _n_coeff(inputs):
        """SH coefficient count the node will fit, from the acquisition.

        Reuses the node's own helpers on a gradient table built from the same
        bval/bvec files the node reads, so the estimator and the node can never
        disagree on the adaptive ``sh_order_max``.
        """
        from dipy.core.gradients import gradient_table
        from dipy.io.gradients import read_bvals_bvecs
        from swane.nipype_pipeline.nodes.DipyCsdFit import (
            n_directions_from_gtab,
            sh_order_for_directions,
        )

        bvals, bvecs = read_bvals_bvecs(inputs.bval, inputs.bvec)
        gtab = gradient_table(bvals, bvecs=bvecs)
        sh_order = sh_order_for_directions(n_directions_from_gtab(gtab))
        return (sh_order + 1) * (sh_order + 2) // 2

    @staticmethod
    def _declared_workers(inputs):
        """The pool size the workflow asked for (the ladder's top rung)."""
        if isdefined(getattr(inputs, "num_threads", None)):
            return max(1, int(inputs.num_threads))
        return 1

    def per_voxel_bytes(self, n_coeff):
        """Bytes one full-volume copy of the output arrays costs per voxel."""
        return self.PEAK_BYTES_PER_VOXEL + self.SH_BYTES_PER_COEFF * int(n_coeff)

    def estimate_gb(self, voxels, volumes, n_coeff, procs):
        """Peak RSS of the whole process tree at ``procs`` workers."""
        procs = max(1, int(procs))
        per_voxel = self.per_voxel_bytes(n_coeff) / 1024**3
        data_gb = self.DATA_BYTES_PER_VOXEL_VOLUME * voxels * volumes / 1024**3

        if procs == 1:
            total = self.OVERHEAD_GB + data_gb + self.SERIAL_COPIES * per_voxel * voxels
        else:
            total = (
                self.OVERHEAD_GB
                + data_gb
                + self.PARALLEL_COPIES * per_voxel * voxels
                + per_voxel * voxels / procs
                + procs * self.SPAWN_GB_PER_WORKER
            )
        return float(self.clamp(total, self.min_gb, None))

    def bottom_rung_gb(self, voxels, volumes, n_coeff):
        """The estimate at the bottom of the ladder (the serial branch)."""
        return self.estimate_gb(voxels, volumes, n_coeff, 1)

    def best_procs_for_budget(self, voxels, volumes, n_coeff, ram_budget_gb, declared):
        """The largest worker count whose estimate fits ``ram_budget_gb``.

        The estimate is not monotone in ``P``, so this scans every rung from
        ``declared`` down to 1 rather than closing the form or halving: a budget
        can admit ``P=4`` and refuse ``P=2``, and stopping at the first failure
        on the way down would discard a rung that fits. Returns 1 (the serial
        branch) when nothing fits -- the caller reports that as an exhausted
        ladder.
        """
        declared = max(1, int(declared))
        for procs in range(declared, 0, -1):
            if self.estimate_gb(voxels, volumes, n_coeff, procs) <= ram_budget_gb:
                return procs
        return 1

    def __call__(self, inputs):
        """One-way estimate at the declared (untuned) worker count."""
        voxels, volumes = self._shape(inputs)
        n_coeff = self._n_coeff(inputs)
        procs = self._declared_workers(inputs)
        mem_gb = self.estimate_gb(voxels, volumes, n_coeff, procs)
        return mem_gb, (
            "voxels=%d, volumes=%d, coeff=%d, workers=%d (untuned), "
            "estimated RAM=%.2f GB" % (voxels, volumes, n_coeff, procs, mem_gb)
        )

    def negotiate(self, inputs, ram_budget_gb):
        """Reserve RAM and tune the worker count to the budget.

        Returns the largest worker count that fits. When even the serial rung
        exceeds the budget it is returned anyway, and said so in the debug
        trace: the generation-time RAM gate is what guarantees a permitted host
        can run the bottom rung, so refusing here would turn a tight fit into a
        dead workflow instead of a slow one.
        """
        from swane.patches.nipype_patches import RamPlan

        voxels, volumes = self._shape(inputs)
        n_coeff = self._n_coeff(inputs)
        declared = self._declared_workers(inputs)

        chosen = self.best_procs_for_budget(
            voxels, volumes, n_coeff, ram_budget_gb, declared
        )
        mem_gb = self.estimate_gb(voxels, volumes, n_coeff, chosen)
        exhausted = mem_gb > ram_budget_gb

        debug = (
            "voxels=%d, volumes=%d, coeff=%d, workers %d -> %d, budget=%.2f GB, "
            "estimated RAM=%.2f GB (%s branch)"
            % (
                voxels,
                volumes,
                n_coeff,
                declared,
                chosen,
                ram_budget_gb,
                mem_gb,
                "serial" if chosen == 1 else "parallel",
            )
        )
        if exhausted:
            debug += " (ladder exhausted: serial rung still exceeds the budget)"

        return RamPlan(
            mem_gb=mem_gb,
            tuned_params={"num_threads": chosen},
            n_procs=chosen,
            debug_str=debug,
        )


def _trx_counts(path):
    """Return ``(n_points, n_streamlines)`` from a ``.trx`` header alone.

    Reads the memory-mapped header (``NB_VERTICES``/``NB_STREAMLINES``) without
    materialising the streamline arrays.
    """
    from trx.trx_file_memmap import load as trx_load

    trx = trx_load(str(path))
    try:
        return int(trx.header["NB_VERTICES"]), int(trx.header["NB_STREAMLINES"])
    finally:
        trx.close()


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipySlrRamEstimator(RamEstimator):
    """
    RAM estimator for :class:`DipyAtlasSLR` -- one-way, no quality-neutral lever.

    Model
    -----
    :class:`DipyAtlasSLR` fits the transform on a fixed-size random subsample
    of the subject tractogram, applies the resulting affine to the full
    tractogram in place, and writes it through pre-allocated memmaps, so the
    peak tracks the full tractogram's point count (loaded, transformed and
    written) while the subsample-fit and the fixed-size atlas side fold into
    the intercept::

        mem_gb = OVERHEAD_GB + BYTES_PER_POINT * n_points / 2**30

    One-way: ``num_threads`` only pins BLAS/OMP threading for the optimisation
    and does not change peak RSS, and the subsample size is fixed (it drives
    quality, not the peak, which is bound by the full-tractogram load/write).

    Calibration
    -----------
    Isolated tree-peak RSS of the real node on three real, current-pipeline
    subject tractograms (points -> measured GB): 121.1M -> 4.348, 67.9M ->
    3.643, 119.7M -> 4.386. A least-squares fit gives ~14 B/point, ~2.7 GB
    overhead (the fixed cost is the atlas load, the dipy imports and the trx
    load/write machinery); the constants below round up to keep a ~1.16x
    margin over every measured point.

    :class:`DipyTissueRamEstimator`'s one-way floor is now higher, so
    ``ResourceManager.DIPY_TRACTOGRAPHY_RAM_REQUIREMENT`` is no longer sourced
    from this node; the estimator still reads it for its static fall-back.
    """

    #: Bytes per subject-tractogram point. Fit ~14 B, rounded up.
    BYTES_PER_POINT = 18

    #: Fixed overhead (interpreter, numpy/dipy/trx/nibabel + the fixed-size
    #: atlas tractogram + the trx load/write machinery). Fit ~2.7 GB, rounded up.
    OVERHEAD_GB = 3.0

    #: No SLR run fits in less than this, whatever the input.
    MIN_GB = 0.5

    #: Static reservation the workflow declares on the node. Read only when
    #: the negotiation cannot run at all (see
    #: ``MonitoredMultiProcPlugin._negotiate_ram``). Sourced from
    #: ``ResourceManager.dipy_tractography_ram_requirements`` -- the same number
    #: the "enable dipy tractography" preference gate checks -- so the node's
    #: fall-back can never exceed the RAM the gate guarantees a permitted host.
    STATIC_FALLBACK_GB = ResourceManager.dipy_tractography_ram_requirements()

    def __init__(self):
        super().__init__(
            input_multipliers={},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )

    def estimate_gb(self, n_points):
        total = self.OVERHEAD_GB + self.BYTES_PER_POINT * int(n_points) / 1024**3
        return float(self.clamp(total, self.min_gb, None))

    def __call__(self, inputs):
        n_points, n_streamlines = _trx_counts(inputs.tractogram)
        mem_gb = self.estimate_gb(n_points)
        return mem_gb, (
            "points=%d, streamlines=%d, estimated RAM=%.2f GB"
            % (n_points, n_streamlines, mem_gb)
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class RecoBundlesRamEstimator(RamEstimator):
    """
    RAM estimator for the RecoBundles build and recognise nodes.

    Model
    -----
    The peak tracks the total point count of the ``tractogram_chunk`` the node
    loads::

        mem_gb = OVERHEAD_GB + BYTES_PER_POINT * n_points / 2**30

    The point count is read from the ``.trx`` header, never by loading the
    streamlines. It is a one-way estimator (no quality-neutral lever): it
    reserves RAM and inherits the default :meth:`negotiate` (empty tuning).

    Chunk-sizing
    ------------
    :meth:`min_chunks_for_budget` inverts the model to the smallest number of
    equal-point chunks whose per-chunk estimate fits a RAM budget, capped by
    :attr:`MIN_STREAMLINES_PER_CHUNK`. It is what the chunker's estimator calls
    to choose ``n_chunks`` (see :class:`DipyRecoBundlesChunkerRamEstimator`).
    """

    #: Bytes per streamline point of the loaded chunk. Conservative bound.
    BYTES_PER_POINT = 40

    #: Fixed overhead (interpreter, numpy/dipy/trx/nibabel).
    OVERHEAD_GB = 0.5

    #: No build/recognise fits in less than this, whatever the input.
    MIN_GB = 0.5

    #: The smallest streamline count a forced split may leave in one chunk; it
    #: caps ``n_chunks`` at ``n_streamlines // MIN_STREAMLINES_PER_CHUNK``.
    MIN_STREAMLINES_PER_CHUNK = 100_000

    #: Static reservation used only when the negotiation cannot run (see
    #: ``MonitoredMultiProcPlugin._negotiate_ram``) -- e.g. the ``.trx`` header
    #: could not be read, a state in which the node cannot run either.
    STATIC_FALLBACK_GB = 6.0

    def __init__(self):
        # max_gb is deliberately None: clamping the estimate down would make the
        # node under-reserve and silently co-schedule with other heavy work.
        super().__init__(
            input_multipliers={},
            overhead_gb=self.OVERHEAD_GB,
            min_gb=self.MIN_GB,
            max_gb=None,
        )

    def estimate_gb(self, n_points):
        """Reservation for a node loading ``n_points`` streamline points."""
        total = self.OVERHEAD_GB + self.BYTES_PER_POINT * int(n_points) / 1024**3
        return float(self.clamp(total, self.min_gb, None))

    def max_chunks(self, n_streamlines):
        """The largest ``n_chunks`` the streamline floor permits."""
        return max(1, int(n_streamlines) // self.MIN_STREAMLINES_PER_CHUNK)

    def min_chunks_for_budget(self, total_points, n_streamlines, ram_budget_gb):
        """The smallest ``n_chunks`` whose per-chunk estimate fits the budget.

        Solves ``OVERHEAD_GB + BYTES_PER_POINT * total_points / n <= budget`` for
        ``n``, clamped to ``[1, max_chunks(n_streamlines)]``. When even
        ``max_chunks`` does not fit, ``max_chunks`` is returned (the caller
        reports it as an exhausted split).
        """
        cap = self.max_chunks(n_streamlines)
        headroom = ram_budget_gb - self.OVERHEAD_GB
        if headroom <= 0:
            return cap
        chunk_gb = self.BYTES_PER_POINT * int(total_points) / 1024**3
        n = math.ceil(chunk_gb / headroom)
        return max(1, min(cap, int(n)))

    def __call__(self, inputs):
        """One-way estimate from the node's ``tractogram_chunk`` point count."""
        n_points, n_streamlines = _trx_counts(inputs.tractogram_chunk)
        mem_gb = self.estimate_gb(n_points)
        return mem_gb, (
            "points=%d, streamlines=%d, estimated RAM=%.2f GB"
            % (n_points, n_streamlines, mem_gb)
        )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.utils.ram_estimator.RamEstimator)  -*-
class DipyRecoBundlesChunkerRamEstimator(RamEstimator):
    """
    RAM estimator for :class:`DipyTractogramChunker` that also decides
    ``n_chunks``.

    The chunker itself is a whole-tractogram load + strided write, so it
    reserves from the whole tractogram's point count. Its :meth:`negotiate`
    additionally chooses ``n_chunks`` so that each downstream RecoBundles chunk
    fits the RAM budget, using :class:`RecoBundlesRamEstimator`'s model, and
    injects it as the tuned ``n_chunks`` parameter (applied to the node before
    it runs).
    """

    def __init__(self):
        self._downstream = RecoBundlesRamEstimator()
        super().__init__(
            input_multipliers={},
            overhead_gb=RecoBundlesRamEstimator.OVERHEAD_GB,
            min_gb=RecoBundlesRamEstimator.MIN_GB,
            max_gb=None,
        )

    def estimate_gb(self, n_points):
        """The chunker's own reservation (whole-tractogram load + write)."""
        return self._downstream.estimate_gb(n_points)

    def __call__(self, inputs):
        """One-way estimate from the whole tractogram's point count."""
        n_points, n_streamlines = _trx_counts(inputs.tractogram_atlas)
        mem_gb = self.estimate_gb(n_points)
        return mem_gb, (
            "points=%d, streamlines=%d, estimated RAM=%.2f GB"
            % (n_points, n_streamlines, mem_gb)
        )

    def negotiate(self, inputs, ram_budget_gb):
        """Reserve the chunker's RAM and choose ``n_chunks`` for the budget."""
        from swane.patches.nipype_patches import RamPlan

        n_points, n_streamlines = _trx_counts(inputs.tractogram_atlas)
        n_chunks = self._downstream.min_chunks_for_budget(
            n_points, n_streamlines, ram_budget_gb
        )
        mem_gb = self.estimate_gb(n_points)
        per_chunk_gb = self._downstream.estimate_gb(n_points / n_chunks)
        exhausted = (
            n_chunks == self._downstream.max_chunks(n_streamlines)
            and per_chunk_gb > ram_budget_gb
        )

        debug = (
            "points=%d, streamlines=%d, budget=%.2f GB, n_chunks -> %d, "
            "downstream RAM/chunk=%.2f GB, chunker RAM=%.2f GB"
            % (
                n_points,
                n_streamlines,
                ram_budget_gb,
                n_chunks,
                per_chunk_gb,
                mem_gb,
            )
        )
        if exhausted:
            debug += " (split exhausted: chunk still exceeds the budget)"

        return RamPlan(
            mem_gb=mem_gb,
            tuned_params={"n_chunks": n_chunks},
            n_procs=None,
            debug_str=debug,
        )
