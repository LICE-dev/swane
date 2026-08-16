"""Command line entry point for the pre-release sweep.

    python -m swane.tests.prerelease --cores 8 --ram 10

The sweep takes hours, so it is deliberately a command rather than a pytest
run: progress is persisted after every pass, ``--resume`` (the default) picks
up where an interrupted run stopped, and everything it produced stays on disk
for inspection.

Useful variants::

    # see what would run on this machine, without running anything
    python -m swane.tests.prerelease --dry-run

    # include the slow FreeSurfer passes
    python -m swane.tests.prerelease --cores 8 --ram 10 --with-reconall

    # re-check results already on disk, without re-running the workflows
    python -m swane.tests.prerelease --checks-only

    # one pass at a time
    python -m swane.tests.prerelease --only dti_tractography
"""

from __future__ import annotations

import argparse
import os
import sys

from swane.utils.ResourceManager import ResourceManager

DEFAULT_WORK_DIR = os.path.join(os.path.expanduser("~"), "test_swane", "prerelease")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m swane.tests.prerelease",
        description=(
            "Run every SWANe workflow over the synthetic phantom exam across "
            "the configuration matrix, then check the results."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    resources = parser.add_argument_group("resources given to each workflow")
    resources.add_argument(
        "--cores",
        type=int,
        default=ResourceManager.get_default_cpu(),
        help="CPU cores for the MonitoredMultiProcPlugin (default: %(default)s)",
    )
    resources.add_argument(
        "--ram",
        type=float,
        default=ResourceManager.get_default_ram(),
        help="RAM budget in GB for the plugin (default: %(default).1f)",
    )

    selection = parser.add_argument_group("what to run")
    selection.add_argument(
        "--with-reconall",
        action="store_true",
        help="include the slow FreeSurfer recon-all passes (hours each)",
    )
    selection.add_argument(
        "--only",
        metavar="PASS",
        nargs="+",
        help="run only these passes (see --list)",
    )
    selection.add_argument(
        "--list", action="store_true", help="list the passes and exit"
    )
    selection.add_argument(
        "--dry-run",
        action="store_true",
        help="show the plan and the host capabilities, run nothing",
    )
    selection.add_argument(
        "--checks-only",
        action="store_true",
        help="re-check results already on disk without running any workflow",
    )

    behaviour = parser.add_argument_group("behaviour")
    behaviour.add_argument(
        "--work-dir",
        default=DEFAULT_WORK_DIR,
        help="where subjects, logs and reports go (default: %(default)s)",
    )
    behaviour.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore previous results and run everything again",
    )
    behaviour.add_argument(
        "--retry-failed",
        action="store_true",
        help="when resuming, re-run passes that previously failed",
    )
    behaviour.add_argument(
        "--rebuild-phantom",
        action="store_true",
        help="regenerate the phantom DICOM even if a cached copy exists",
    )
    behaviour.add_argument(
        "--full-accuracy",
        action="store_true",
        help="disable test_run speed shortcuts (subsampling, reduced "
        "iterations/samples, ...) and run every pass at full accuracy, "
        "like a real analysis; slower",
    )
    behaviour.add_argument(
        "--no-ground-truth",
        action="store_true",
        help="skip the anatomical plausibility checks (they rebuild the "
        "phantom tissue model, which needs FreeSurfer and some memory)",
    )
    behaviour.add_argument(
        "--slicer",
        default=os.environ.get("SWANE_SLICER_PATH", ""),
        help="path to the Slicer executable, needed by the venous CT passes "
        "(default: whatever the user's ~/.SWANe configuration records)",
    )
    behaviour.add_argument(
        "-v", "--verbose", action="store_true", help="print every node as it starts"
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Imported late so --help and --list stay instant.
    from swane.tests.prerelease import capabilities as caps_mod
    from swane.tests.prerelease import report as report_mod
    from swane.tests.prerelease.checks import GroundTruth, check_pass
    from swane.tests.prerelease.plan import (
        PASSES,
        build_plan,
        coverage,
        describe_plan,
    )

    if args.list:
        for spec in PASSES:
            tag = " (opt-in: --with-reconall)" if spec.heavy_freesurfer else ""
            print("%-28s %s%s" % (spec.name, spec.description, tag))
        return 0

    work_dir = os.path.abspath(args.work_dir)
    os.makedirs(work_dir, exist_ok=True)

    # Slicer comes from the user's real SWANe settings unless overridden: that
    # is where the application records it after validating the version.
    slicer_path = args.slicer or user_slicer_path()
    if slicer_path:
        print("Slicer: %s" % slicer_path)
    global_config = _slicer_probe_config(slicer_path)

    caps = caps_mod.probe(
        global_config=global_config, cores=args.cores, ram_gb=args.ram
    )
    print(caps.describe())
    print("")

    plan = build_plan(caps, with_reconall=args.with_reconall, only=args.only)
    cover = coverage(plan, caps)
    print(describe_plan(plan, cover))
    print("")

    blocking = caps_mod.blocking_failures(caps)
    if blocking and not args.dry_run:
        print("Cannot run:")
        for cap in blocking:
            print("  - %s: %s" % (cap.name, cap.reason))
        return 2

    if args.dry_run:
        print("Dry run: nothing was executed.")
        return 0

    if not [p for p in plan if not p.skipped]:
        print("No pass can run on this host with these options.")
        return 2

    from swane.tests.prerelease.runner import run_sweep
    from swane.tests.prerelease.subject import load_phantom

    ground_truth = None
    if not args.no_ground_truth:
        print("Building the phantom ground truth for the anatomical checks...")
        try:
            ground_truth = GroundTruth.build()
        except Exception as exc:
            print("  could not build it (%s); those checks are skipped." % exc)

    if args.checks_only:
        results = _reload_results(work_dir, plan)
    else:
        print("Preparing the phantom exam (generated once, then cached)...")
        exam = load_phantom(force=args.rebuild_phantom)
        print("  %s" % exam.root)
        print("")
        results = run_sweep(
            plan,
            exam,
            work_dir,
            cores=args.cores,
            ram_gb=args.ram,
            slicer_path=slicer_path,
            resume=not args.no_resume,
            retry_failed=args.retry_failed,
            verbose=args.verbose,
            test_run=not args.full_accuracy,
        )

    print("")
    print("Checking results...")
    for result in results:
        result.checks = check_pass(result, ground_truth)
        if result.status == "skipped":
            continue
        print("  %s" % result.name)
        for check in result.checks:
            if not check.passed:
                print(str(check))

    report = report_mod.build_report(
        results,
        caps,
        cover,
        work_dir,
        options={
            "cores": args.cores,
            "ram_gb": args.ram,
            "with_reconall": args.with_reconall,
            "only": args.only,
            "ground_truth": ground_truth is not None,
            "test_run": not args.full_accuracy,
        },
    )
    json_path = report_mod.write_json(report, work_dir)
    html_path = report_mod.write_html(report, work_dir)
    report_mod.print_summary(report)
    print("Report: %s" % html_path)
    print("        %s" % json_path)
    print("Results kept under: %s" % work_dir)

    return 0 if report_mod.overall_success(report) else 1


def user_slicer_path() -> str:
    """Read the Slicer path out of the user's real SWANe configuration.

    SWANe stores it in ``~/.SWANe`` once Slicer has been configured (and
    version-validated) in the application, so that file — not an environment
    variable — is the natural source for anyone running this sweep.

    Deliberately read-only: instantiating :class:`ConfigManager` on the real
    file would rewrite it as a side effect of loading, and a test suite has no
    business editing the user's settings.
    """
    import configparser

    from swane import strings
    from swane.config.config_enums import GlobalPrefCategoryList

    path = os.path.join(os.path.expanduser("~"), "." + strings.APPNAME)
    if not os.path.isfile(path):
        return ""
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
        return parser.get(
            str(GlobalPrefCategoryList.MAIN), "slicer_path", fallback=""
        ).strip()
    except configparser.Error:
        return ""


def _slicer_probe_config(slicer_path: str):
    """A throwaway global config carrying only the Slicer path, for probing."""
    if not slicer_path:
        return None
    try:
        import tempfile

        from swane.config.ConfigManager import ConfigManager
        from swane.config.config_enums import GlobalPrefCategoryList

        folder = tempfile.mkdtemp(prefix="swane_probe_")
        config = ConfigManager(global_base_folder=folder)
        config[GlobalPrefCategoryList.MAIN]["slicer_path"] = slicer_path
        return config
    except Exception:
        return None


def _reload_results(work_dir: str, plan: list) -> list:
    """Rebuild PassResult objects from a previous run, for ``--checks-only``."""
    from swane.tests.prerelease.runner import PassResult, load_state

    state = load_state(work_dir)
    results = []
    for item in plan:
        stored = state.get(item.name)
        if not stored:
            results.append(
                PassResult(
                    name=item.name,
                    status="skipped",
                    reason="no recorded result in %s" % work_dir,
                )
            )
            continue
        results.append(
            PassResult(
                **{k: v for k, v in stored.items() if k in PassResult.__annotations__}
            )
        )
    return results


if __name__ == "__main__":
    sys.exit(main())
