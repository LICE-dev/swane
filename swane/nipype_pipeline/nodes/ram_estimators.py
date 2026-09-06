# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import math

import numpy as np
import nibabel as nib
from nipype.interfaces.base import isdefined
from nipype.utils.ram_estimator import RamEstimator


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
    when a tight FOV still holds the whole brain. ``seeds`` is the WM-dominant
    voxel count of the ``pve_wm`` mask times ``seed_density`` (user decision,
    2026-09-06), which is what the buffer lever scales.

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
        """WM-dominant voxels in ``pve_wm`` times ``seed_density`` -- the seed
        pool the buffer lever scales. Reads the mask (user decision,
        2026-09-06), never the SH data."""
        from swane.nipype_pipeline.nodes.DipyTracking import wm_seed_mask

        density = int(inputs.seed_density) if isdefined(inputs.seed_density) else 2
        pve = nib.load(inputs.pve_wm).get_fdata()
        return int(wm_seed_mask(pve).sum()) * density

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
