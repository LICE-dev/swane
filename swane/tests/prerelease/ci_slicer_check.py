"""Validate a CI Slicer install through SWANe's own Slicer dependency check.

Runs ``SlicerCheckWorker`` synchronously on the Slicer at ``$SWANE_SLICER_PATH``
(or ``--slicer``): the same code path the application runs, which checks the
version and installs the extensions SWANe needs (``DependencyManager.
SLICER_MODULES``) from Slicer's extension server. Exits non-zero unless Slicer
is DETECTED with every extension, so a CI job fails here instead of silently
dropping the Slicer passes.

Usage::

    python -m swane.tests.prerelease.ci_slicer_check [--slicer PATH]
"""

import argparse
import os
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--slicer",
        default=os.environ.get("SWANE_SLICER_PATH", ""),
        help="Slicer executable (default: $SWANE_SLICER_PATH)",
    )
    args = parser.parse_args(argv)
    if not args.slicer or not os.path.exists(args.slicer):
        print("No Slicer executable at %r" % args.slicer)
        return 1

    from swane.utils.DependencyManager import DependenceStatus
    from swane.workers.SlicerCheckWorker import SlicerCheckWorker

    result = {}
    worker = SlicerCheckWorker(args.slicer)
    worker.signal.slicer.connect(
        lambda cmd, version, label, state: result.update(
            cmd=cmd, version=version, label=label, state=state
        )
    )
    worker.signal.extensions.connect(lambda state: result.update(extensions=state))
    # Synchronous: same-thread signal emissions call the slots directly.
    worker.run()

    print("Slicer: %s" % result.get("cmd"))
    print("Version: %s" % result.get("version"))
    print("State: %s" % result.get("state"))
    print("Label: %s" % result.get("label"))
    print("Extensions: %s" % result.get("extensions"))
    if result.get("state") != DependenceStatus.DETECTED:
        return 1
    # The check may fall back to a filesystem search: make sure it validated
    # the Slicer CI installed, not another one.
    if os.path.realpath(result["cmd"]) != os.path.realpath(args.slicer):
        print("The check found a different Slicer than %s" % args.slicer)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
