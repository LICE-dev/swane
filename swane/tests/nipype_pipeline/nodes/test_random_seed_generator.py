"""Unit tests for :class:`swane.nipype_pipeline.nodes.RandomSeedGenerator`.

The interface only draws random integers and depends on ``mask`` merely to
force an ordering dependency, so it runs without any neuroimaging tool.
"""

import pytest

from swane.nipype_pipeline.nodes.RandomSeedGenerator import RandomSeedGenerator


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
        """Every generated seed is an ``int`` in ``[0, 1000)``.

        The seeds feed probabilistic tractography, so they must be plain
        integers within the ``randrange(1000)`` domain.
        """
        iface = RandomSeedGenerator()
        iface.inputs.seeds_n = 20
        iface.inputs.mask = mask_file

        result = iface.run()
        assert all(0 <= seed < 1000 for seed in result.outputs.seeds)
        assert all(isinstance(seed, int) for seed in result.outputs.seeds)

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
