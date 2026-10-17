"""Harness for the bash installer ``installer/install_swane.sh``.

The tests ``source`` the script (its ``main`` runs only when the file is
executed) and call one function at a time in a fresh ``bash``. Each call runs
in an isolated environment so nothing of the developer machine can leak in or
be reached:

* the environment is rebuilt from scratch (no inherited ``FSLDIR``,
  ``CONDA_EXE``, ``CONDA_PREFIX``, ``SHELL``...): only ``HOME``, ``PATH``,
  ``TMPDIR``, ``LANG``/``LC_ALL=C``, ``SWANE_TTY`` and the
  ``SWANE_SYSTEM_*`` overrides, plus what the test passes;
* ``PATH`` is ``<stubdir>:<toolsdir>``. ``toolsdir`` holds symlinks to a
  whitelist of basic utilities (:data:`BASIC_TOOLS`); every tool under test
  (``uname``, ``conda``, ``sudo``, ``apt-get``, ``curl``, ``sha256sum``,
  ``dot``, ``python``...) exists only when the test stubs it, so the real
  ones can never run;
* ``HOME`` is ``<tmp_path>/home`` and prompts read ``SWANE_TTY``, a file of
  scripted answers, never the real terminal.

The fixtures that build these objects live in ``conftest.py``.
"""

import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "installer" / "install_swane.sh"

#: Utilities the script may call that are never under test. Resolved with
#: ``shutil.which`` on the host and symlinked into a per-session directory.
BASIC_TOOLS = (
    "bash",
    "sh",
    "cat",
    "sed",
    "grep",
    "awk",
    "mkdir",
    "rm",
    "rmdir",
    "chmod",
    "cp",
    "mv",
    "ln",
    "touch",
    "dirname",
    "basename",
    "tr",
    "head",
    "tail",
    "cut",
    "sort",
    "uniq",
    "wc",
    "printf",
    "env",
    "mktemp",
    "readlink",
    "ls",
    "tee",
    "test",
    "true",
    "false",
    "expr",
)
#: Tools whose absence makes the harness meaningless.
REQUIRED_TOOLS = (
    "bash",
    "cat",
    "sed",
    "grep",
    "mkdir",
    "rm",
    "chmod",
    "dirname",
    "tr",
    "mktemp",
)

#: The host bash: every stub and every call runs with it.
BASH = shutil.which("bash")


def bash_quote(text: str) -> str:
    """Quote ``text`` as one single-quoted bash word."""
    return "'" + text.replace("'", "'\\''") + "'"


def link_tools(tools: Path) -> Path:
    """Symlink every available :data:`BASIC_TOOLS` entry into ``tools``.

    Raises
    ------
    RuntimeError
        If one of :data:`REQUIRED_TOOLS` is not on the host ``PATH``.
    """
    for name in BASIC_TOOLS:
        target = shutil.which(name)
        if target is None:
            if name in REQUIRED_TOOLS:
                raise RuntimeError("installer harness needs %s on PATH" % name)
            continue
        (tools / name).symlink_to(target)
    return tools


def make_executable(path: Path, body: str) -> Path:
    """Write a bash script at ``path`` (parents created) and make it executable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!%s\n%s\n" % (BASH, body))
    path.chmod(0o755)
    return path


def make_conda_root(root: Path) -> Path:
    """Create a fake conda root (``etc/profile.d/conda.sh`` and ``bin/conda``)."""
    (root / "etc" / "profile.d").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "profile.d" / "conda.sh").write_text("# fake conda.sh\n")
    make_executable(root / "bin" / "conda", "exit 0")
    return root


class Stubs:
    """Executable stubs in a private directory placed first on ``PATH``.

    Every stub appends one line to :attr:`calls_log` (its name followed by its
    arguments, space-separated) before running its body, so tests can assert
    on the order and arguments of every external call.

    Parameters
    ----------
    stubdir : Path
        Directory of the stubs (created by the ``stub`` fixture).
    """

    def __init__(self, stubdir: Path):
        self.dir = stubdir
        self.calls_log = stubdir / "calls.log"

    def __call__(self, name: str, body: str = "") -> Path:
        """Write the stub ``name``; ``body`` is bash run after logging.

        In ``body``, ``"$@"`` holds the stub's arguments and ``$CALLS_LOG``
        the log path (for helpers that log their own lines).
        """
        log = bash_quote(str(self.calls_log))
        return make_executable(
            self.dir / name,
            "CALLS_LOG=%s\n"
            'printf "%%s" %s >> "$CALLS_LOG"\n'
            'for _arg in "$@"; do printf " %%s" "$_arg" >> "$CALLS_LOG"; done\n'
            'printf "\\n" >> "$CALLS_LOG"\n'
            "%s" % (log, bash_quote(name), body),
        )

    def calls(self, name: str = None) -> list:
        """Logged calls (lines), optionally only those of the stub ``name``."""
        if not self.calls_log.exists():
            return []
        lines = self.calls_log.read_text().splitlines()
        if name is None:
            return lines
        return [line for line in lines if line == name or line.startswith(name + " ")]

    def platform(self, system: str, machine: str) -> Path:
        """Stub ``uname``: ``uname``/``uname -s`` print ``system``, ``-m`` ``machine``."""
        return self(
            "uname",
            'case "${1:-}" in\n'
            "    -m) echo %s ;;\n"
            "    *) echo %s ;;\n"
            "esac" % (bash_quote(machine), bash_quote(system)),
        )


class Runner:
    """Run installer functions in an isolated ``bash`` (see the module docstring).

    Parameters
    ----------
    tmp_path : Path
        The test's temporary directory; ``home``, ``tmp`` and ``tty`` live in it.
    stubs : Stubs
        The stubs placed first on ``PATH``.
    tools : Path
        The directory made by :func:`link_tools`.
    """

    def __init__(self, tmp_path: Path, stubs: Stubs, tools: Path):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.tmpdir = tmp_path / "tmp"
        self.tmpdir.mkdir()
        self.stubs = stubs
        self.tools = tools
        self.tty_path = tmp_path / "tty"
        self.path = "%s:%s" % (stubs.dir, tools)

    def environment(self, env=None, tty=None) -> dict:
        """The whole environment of one call (``env`` values of None unset)."""
        if tty is not None:
            self.tty_path.write_text(tty)
        base = {
            "HOME": str(self.home),
            "PATH": self.path,
            "TMPDIR": str(self.tmpdir),
            "LANG": "C",
            "LC_ALL": "C",
            "SWANE_TTY": str(self.tty_path),
            "SWANE_SYSTEM_CONDA_ROOTS": str(self.tmp / "no-system-conda"),
            "SWANE_SYSTEM_FSL_DIRS": str(self.tmp / "no-system-fsl"),
        }
        for key, value in (env or {}).items():
            if value is None:
                base.pop(key, None)
            else:
                base[key] = str(value)
        return base

    def __call__(
        self, func: str, *args, env=None, tty=None, input=None, timeout=30
    ) -> subprocess.CompletedProcess:
        """Source the script and run ``func args...``.

        Parameters
        ----------
        func : str
            Installer function (or any command) to run after sourcing.
        *args
            Its arguments (converted with ``str``).
        env : dict, optional
            Variables added to the isolated environment; a value of None
            removes the variable. A ``PATH`` given here replaces
            ``<stubdir>:<toolsdir>`` (build it from :attr:`path`).
        tty : str, optional
            Scripted terminal answers, one per line, written to ``SWANE_TTY``.
            Without it ``SWANE_TTY`` does not exist (no terminal) unless an
            earlier call of the same test wrote it.
        input : str, optional
            Standard input (default: empty).
        timeout : float, optional
            Seconds before the call is killed (a hang fails the test).

        Returns
        -------
        subprocess.CompletedProcess
            With text ``stdout`` and ``stderr``.
        """
        argv = ['source "$0"; "$@"', str(SCRIPT), func, *map(str, args)]
        return self._run(argv, env, tty, input, timeout)

    def code(self, snippet: str, env=None, tty=None, input=None, timeout=30):
        """Source the script, then run the bash ``snippet`` (options as above)."""
        argv = ['source "$0"; ' + snippet, str(SCRIPT)]
        return self._run(argv, env, tty, input, timeout)

    def _run(self, bash_c_args, env, tty, input, timeout):
        return subprocess.run(
            [BASH, "-c", *bash_c_args],
            env=self.environment(env, tty),
            cwd=str(self.tmp),
            input=input if input is not None else "",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
