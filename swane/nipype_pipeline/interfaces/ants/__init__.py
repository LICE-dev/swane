# -*- coding: utf-8 -*-

# Fixed seed for the random metric sampling of the ANTs registrations
# (antsRegistration --random-seed, set through ants.config._random_seed). Any
# non-zero integer is valid; 123 is the default seed of antspyx's own
# deterministic mode (ants.config). It makes the sampling reproducible; the
# output is bit-identical run to run only with a single ITK thread, because
# multithreaded metric sums are accumulated in a non-deterministic order.
DEFAULT_RANDOM_SEED = 123
