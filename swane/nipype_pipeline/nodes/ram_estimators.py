from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import NipypeRamEstimator

class FlirtRamEstimator(NipypeRamEstimator):
    """
    RAM estimator for FSL FLIRT with calibrated multipliers and overhead.
    """
    def __init__(self):
        # Set FLIRT-specific parameters
        super().__init__(
            input_multipliers={
                'in_file':12,       # main input
                'reference':2,      # reference
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
                'in_file': 24,    # contributes, but secondary
                'ref_file': 200,   # warp field + gradients + pyramid
            },
            overhead_gb=1.8,     # control structures + buffers
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
                'warp': 2,    # contributes, but secondary
                'reference': 48,   # warp field + gradients + pyramid
            },
            overhead_gb=0.3,
            min_gb=0.4,
            max_gb=6.0
        )

class FastRamEstimator(NipypeRamEstimator):
    """
    RAM estimator for FSL FNIRT.
    Calibrated from empirical mem_peak_gb measurements.
    """
    def __init__(self):
        super().__init__(
            input_multipliers={
                'in_files': 110,    # contributes, but secondary
            },
            overhead_gb=0.3,
            min_gb=1,
            max_gb=8
        )
