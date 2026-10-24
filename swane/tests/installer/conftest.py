"""Fixtures for the bash installer tests (the harness is in ``harness.py``)."""

import pytest

from swane.tests.installer.harness import Runner, Stubs, link_tools


@pytest.fixture(scope="session")
def tools_dir(tmp_path_factory):
    """Per-session directory of symlinks to the whitelisted basic utilities."""
    return link_tools(tmp_path_factory.mktemp("installer-tools"))


@pytest.fixture
def stub(tmp_path) -> Stubs:
    """Factory of stub executables, first on the installer's ``PATH``.

    ``stub("conda", 'echo "conda 24.11.3"')`` writes ``<tmp_path>/stubs/conda``;
    every call appends ``conda <args>`` to ``stub.calls_log``
    (``<tmp_path>/stubs/calls.log``), read back with ``stub.calls()``.
    ``stub.platform("Darwin", "arm64")`` stubs ``uname``.
    """
    stubdir = tmp_path / "stubs"
    stubdir.mkdir()
    return Stubs(stubdir)


@pytest.fixture
def sh(tmp_path, stub, tools_dir) -> Runner:
    """Runner of installer functions in an isolated bash.

    ``sh("find_conda", env={...}, tty="y\\n")`` returns a
    ``CompletedProcess``; ``sh.code("snippet")`` runs arbitrary bash after
    sourcing. ``sh.home`` is the ``HOME`` of every call.
    """
    return Runner(tmp_path, stub, tools_dir)
