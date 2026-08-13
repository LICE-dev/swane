"""Unit tests for :class:`swane.nipype_pipeline.nodes.TTest.TTest`.

Pure Python (``scipy.stats.ttest_ind_from_stats``): no neuroimaging tool needed.
"""

from scipy.stats import ttest_ind_from_stats

from swane.nipype_pipeline.nodes.TTest import TTest


class TestTTest:
    """Two-sample t-test computed from summary statistics."""

    def test_matches_scipy_reference(self):
        """Outputs match a direct ``ttest_ind_from_stats`` reference call."""
        lh = [10.0, 2.0, 30]  # mean, std, nobs
        rh = [12.0, 2.5, 30]
        node = TTest()
        node.inputs.stats_lh = lh
        node.inputs.stats_rh = rh

        result = node.run()

        exp_t, exp_p = ttest_ind_from_stats(
            mean1=lh[0], std1=lh[1], nobs1=lh[2],
            mean2=rh[0], std2=rh[1], nobs2=rh[2],
        )
        assert result.outputs.stat_t == exp_t
        assert result.outputs.stat_p == exp_p

    def test_identical_distributions_give_zero_t(self):
        """Identical means yield a t statistic of exactly 0."""
        node = TTest()
        node.inputs.stats_lh = [5.0, 1.0, 20]
        node.inputs.stats_rh = [5.0, 1.0, 20]
        result = node.run()
        assert result.outputs.stat_t == 0.0

    def test_malformed_stats_fall_back_to_zero(self):
        """Malformed (too-short) stat lists are caught and yield 0/0.

        The interface swallows the resulting ``IndexError`` and reports a null
        result rather than crashing the workflow.
        """
        node = TTest()
        node.inputs.stats_lh = [1.0]  # missing std/nobs
        node.inputs.stats_rh = [2.0]
        result = node.run()
        assert result.outputs.stat_t == 0
        assert result.outputs.stat_p == 0
