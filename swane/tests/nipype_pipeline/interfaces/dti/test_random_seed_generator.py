"""Unit tests for :class:`swane.nipype_pipeline.interfaces.dti.RandomSeedGenerator`.

The interface only draws random integers and depends on ``mask`` merely to
force an ordering dependency, so it runs without any neuroimaging tool.
"""

import pytest

from swane.nipype_pipeline.interfaces.dti.RandomSeedGenerator import (
    MAX_SEED,
    MIN_SEED,
    RandomSeedGenerator,
)


@pytest.fixture
def mask_file(tmp_path):
    """A dummy existing file to satisfy the mandatory ``mask`` input."""
    path = tmp_path / "mask.nii.gz"
    path.write_bytes(b"\0")
    return str(path)


class TestRandomSeedGenerator:
    def test_generates_requested_number_of_seeds(self, mask_file):
        """Exactly ``seeds_n`` seeds are produced on the output."""
        iface = RandomSeedGenerator()
        iface.inputs.seeds_n = 5
        iface.inputs.mask = mask_file

        result = iface.run()
        assert len(result.outputs.seeds) == 5

    def test_seeds_are_in_expected_range(self, mask_file):
        """Every generated seed is an ``int`` in ``[MIN_SEED, MAX_SEED)``.

        The seeds become probtrackx2 ``--rseed`` values, so they must be plain
        positive integers that fit a signed 32-bit int.
        """
        iface = RandomSeedGenerator()
        iface.inputs.seeds_n = 20
        iface.inputs.mask = mask_file

        result = iface.run()
        assert all(MIN_SEED <= seed < MAX_SEED for seed in result.outputs.seeds)
        assert all(isinstance(seed, int) for seed in result.outputs.seeds)

    def test_seed_bounds_fit_a_signed_32bit_int(self):
        assert MIN_SEED >= 1
        assert MAX_SEED <= 2**31 - 1

    def test_seeds_are_never_repeated(self, mask_file):
        """A repeated seed makes two probtrackx runs identical, and
        SumMultiTracks would then count that realisation twice."""
        import random

        for state in range(20):
            random.seed(state)
            iface = RandomSeedGenerator()
            iface.inputs.seeds_n = 100  # far more than track_procs' maximum
            iface.inputs.mask = mask_file
            seeds = iface.run().outputs.seeds
            assert len(set(seeds)) == len(seeds) == 100

    def test_zero_seeds_yields_empty_list(self, mask_file):
        """Requesting zero seeds yields an empty list (boundary case)."""
        iface = RandomSeedGenerator()
        iface.inputs.seeds_n = 0
        iface.inputs.mask = mask_file

        result = iface.run()
        assert result.outputs.seeds == []

    def test_seed_list_does_not_leak_between_runs(self, mask_file):
        """Seeds are per-instance state and do not accumulate across runs.

        Each interface starts from an empty ``seed_list``, so two independent
        runs report exactly their own ``seeds_n`` count rather than the sum of
        both (which the previous shared class-attribute implementation did).
        """
        first = RandomSeedGenerator()
        first.inputs.seeds_n = 3
        first.inputs.mask = mask_file
        assert len(first.run().outputs.seeds) == 3

        second = RandomSeedGenerator()
        second.inputs.seeds_n = 4
        second.inputs.mask = mask_file
        assert len(second.run().outputs.seeds) == 4
