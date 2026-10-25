"""Environment and load check of the Matlab Runtime (MCR) of FreeSurfer.

From glibc 2.41, ``dlopen`` refuses a shared library whose ``PT_GNU_STACK``
asks for an executable stack, and many libraries of the R2019b MCR that
FreeSurfer 8 requires do: the runtime then fails to initialize. The
``glibc.rtld.execstack=2`` tunable (glibc 2.42, backported to the 2.41 stable
branch) forces an executable stack at process start, so the libraries load;
older glibc releases ignore it, and macOS has no glibc.

The FreeSurfer Matlab tools always run with :func:`mcr_environ`, and the
dependency check loads the runtime in a child process with that same
environment, so a runtime that still cannot load is reported up front with the
loader message instead of failing at the end of recon-all.
"""

import glob
import os
import subprocess
import sys

EXECSTACK_TUNABLE = "glibc.rtld.execstack=2"
EXECSTACK_ERROR = "cannot enable executable stack"
MCR_BASE_LIBRARY = os.path.join("bin", "glnxa64", "libmwmclbase.so")
# The library folders the MCR launcher scripts put on LD_LIBRARY_PATH
MCR_LIBRARY_DIRS = (
    os.path.join("runtime", "glnxa64"),
    os.path.join("bin", "glnxa64"),
    os.path.join("sys", "os", "glnxa64"),
    os.path.join("sys", "opengl", "lib", "glnxa64"),
)
PROBE_TIMEOUT = 60

_PROBE_CODE = "import ctypes, sys; ctypes.CDLL(sys.argv[1])"


def mcr_environ() -> dict:
    """Variables a FreeSurfer Matlab tool needs on top of the inherited
    environment: the execstack tunable, appended to the user's tunables."""
    tunables = os.environ.get("GLIBC_TUNABLES")
    return {
        "GLIBC_TUNABLES": (
            "%s:%s" % (tunables, EXECSTACK_TUNABLE) if tunables else EXECSTACK_TUNABLE
        )
    }


def find_mcr_root(freesurfer_home: str) -> str | None:
    """The newest ``MCRv*`` folder of ``freesurfer_home`` with the base library."""
    roots = sorted(glob.glob(os.path.join(freesurfer_home, "MCRv*")))
    roots = [r for r in roots if os.path.isfile(os.path.join(r, MCR_BASE_LIBRARY))]
    return roots[-1] if roots else None


def mcr_load_error(mcr_root: str) -> str | None:
    """Load the MCR base library in a child process with the environment of
    the FreeSurfer Matlab tools: None if it loads, else the loader message."""
    env = dict(os.environ)
    env.update(mcr_environ())
    dirs = [os.path.join(mcr_root, d) for d in MCR_LIBRARY_DIRS]
    if env.get("LD_LIBRARY_PATH"):
        dirs.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = os.pathsep.join(dirs)
    try:
        res = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                _PROBE_CODE,
                os.path.join(mcr_root, MCR_BASE_LIBRARY),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    if res.returncode == 0:
        return None
    lines = (res.stderr or "").strip().splitlines()
    return lines[-1] if lines else "exit code %d" % res.returncode


def glibc_version() -> str:
    """The running glibc version (e.g. ``glibc 2.43``), or an empty string."""
    try:
        return os.confstr("CS_GNU_LIBC_VERSION") or ""
    except (AttributeError, ValueError, OSError):
        return ""
