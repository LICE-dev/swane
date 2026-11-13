"""Unit tests for :mod:`swane.utils.decorators`."""

from swane.utils.decorators import debug, timer


def test_debug_preserves_result_and_name():
    @debug
    def add(a, b):
        return a + b

    assert add(2, 3) == 5
    assert add.__name__ == "add"


def test_timer_preserves_result_and_name():
    @timer
    def mul(a, b):
        return a * b

    assert mul(2, 4) == 8
    assert mul.__name__ == "mul"
