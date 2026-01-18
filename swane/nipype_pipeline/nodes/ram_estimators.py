from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import NipypeRamEstimator

class FlirtRamEstimator(NipypeRamEstimator):
    """
    RAM estimator for FSL FLIRT with calibrated multipliers and overhead.
    """
    def __init__(self):
        # Set FLIRT-specific parameters
        super().__init__(
            input_multipliers={
                'in_file':32,       # main input
                'reference':4,      # reference
            },
            overhead_gb=0.30,
            min_gb=0.3,
            max_gb=4.0
        )

class FnirtRamEstimator(NipypeRamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """
    def __init__(self):
        super().__init__(
            input_multipliers={
                'in_file': 32,    # contributes, but secondary
                'ref_file': 180,   # warp field + gradients + pyramid
            },
            overhead_gb=2,     # control structures + buffers
            min_gb=2,          # FNIRT is never really small
            max_gb=8.0
        )

class InvWarpRamEstimator(NipypeRamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """
    def __init__(self):
        super().__init__(
            input_multipliers={
                'warp': 32,    # contributes, but secondary
                'reference': 180,   # warp field + gradients + pyramid
            },
            overhead_gb=2,
            min_gb=2,
            max_gb=8.0
        )

class FastRamEstimator(NipypeRamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """
    def __init__(self):
        super().__init__(
            input_multipliers={
                'in_files': 32,    # contributes, but secondary
            },
            overhead_gb=2,
            min_gb=2,
            max_gb=8.0
        )