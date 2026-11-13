import pytest

from swane.utils import mp_start_method
from swane.utils.mp_start_method import START_METHOD_ENV_VAR, worker_pool_start_method

POSIX_METHODS = ["fork", "spawn", "forkserver"]


@pytest.fixture
def host(monkeypatch):
    """Pretend to run on ``platform`` with ``methods`` available."""

    def _set(platform, methods=POSIX_METHODS):
        monkeypatch.delenv(START_METHOD_ENV_VAR, raising=False)
        monkeypatch.setattr(mp_start_method.sys, "platform", platform)
        monkeypatch.setattr(
            mp_start_method.multiprocessing,
            "get_all_start_methods",
            lambda: list(methods),
        )

    return _set


def test_macos_uses_forkserver(host):
    # fork is not safe on macOS: a worker forked from the workflow process can
    # segfault inside Apple's frameworks (e.g. _scproxy during a download).
    host("darwin")
    assert worker_pool_start_method() == "forkserver"


def test_linux_keeps_fork(host):
    host("linux")
    assert worker_pool_start_method() == "fork"


def test_platform_without_fork_falls_back_to_spawn(host):
    host("win32", methods=["spawn"])
    assert worker_pool_start_method() == "spawn"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_env_override_wins(host, monkeypatch, platform):
    host(platform)
    monkeypatch.setenv(START_METHOD_ENV_VAR, " Spawn ")
    assert worker_pool_start_method() == "spawn"


def test_invalid_env_override_is_ignored_with_a_warning(host, monkeypatch):
    host("darwin")
    monkeypatch.setenv(START_METHOD_ENV_VAR, "threads")
    warnings = []
    monkeypatch.setattr(
        mp_start_method.logger, "warning", lambda *args: warnings.append(args)
    )
    assert worker_pool_start_method() == "forkserver"
    assert len(warnings) == 1
    assert START_METHOD_ENV_VAR in warnings[0]


def test_override_unavailable_on_this_platform_is_ignored(host, monkeypatch):
    host("win32", methods=["spawn"])
    monkeypatch.setenv(START_METHOD_ENV_VAR, "fork")
    assert worker_pool_start_method() == "spawn"
