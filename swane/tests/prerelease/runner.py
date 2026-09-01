"""Execute the planned passes, one at a time, and record what happened.

The passes run **strictly sequentially**. Each one is a full workflow over a
whole exam and will happily use every core and gigabyte it is given, so
overlapping two of them would only make both slower and turn a RAM ceiling into
an OOM kill.

Execution goes through :class:`~swane.workers.WorkflowProcess.WorkflowProcess`,
the very same path the application uses, rather than calling ``workflow.run()``
directly: that keeps the suite honest about what ships (the
``MonitoredMultiProcPlugin``, the resource accounting, the crash-file
handling) and gives per-node signals for free.

A complete sweep takes hours, so progress is persisted after every pass and a
re-run resumes where it stopped instead of starting over.
"""

from __future__ import annotations

import json
import os
import queue as queue_mod
import socket
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from multiprocessing import Queue

import psutil

from swane.nipype_pipeline.engine.WorkflowReport import WorkflowSignals
from swane.utils.DependencyManager import DependencyManager
from swane.tests.prerelease.subject import prepare_subject

#: File holding the state of a sweep, so it can be resumed.
STATE_FILE = "prerelease_state.json"
#: Per-pass result, written inside the pass folder.
PASS_RESULT_FILE = "pass_result.json"
#: Exclusive owner record for a work directory.
LOCK_FILE = ".prerelease.lock"

WORKFLOW_NAME = "prerelease_wf"


@dataclass
class PassResult:
    """What one pass did."""

    name: str
    status: str = "pending"  # completed | failed | skipped | error
    reason: str = ""
    seconds: float = 0.0
    subject_dir: str = ""
    inputs: list = field(default_factory=list)
    values: dict = field(default_factory=dict)
    downgrades: list = field(default_factory=list)
    nodes_started: int = 0
    nodes_completed: int = 0
    node_errors: list = field(default_factory=list)  # {node, workflow, crash_file}
    insufficient_resources: bool = False
    #: Filled in later by the checks module.
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "completed" and not self.node_errors

    def to_json(self) -> dict:
        return asdict(self)


class PrereleaseAlreadyRunningError(RuntimeError):
    """Raised when another sweep owns the requested work directory."""


class PrereleaseWorkDirLock:
    """PID lock protecting a prerelease work directory.

    The complete owner record is hard-linked into place, so contenders never
    observe a half-written PID. A lock left behind by a crashed process is
    removed on the next acquisition after PID and process creation time prove
    that its owner no longer exists.
    """

    def __init__(self, work_dir: str):
        self.work_dir = os.path.abspath(work_dir)
        self.path = os.path.join(self.work_dir, LOCK_FILE)
        process = psutil.Process(os.getpid())
        self.owner = {
            "pid": process.pid,
            "process_create_time": process.create_time(),
            "hostname": socket.gethostname(),
            "acquired_at": time.time(),
            "token": uuid.uuid4().hex,
        }
        self.acquired = False

    def acquire(self):
        os.makedirs(self.work_dir, exist_ok=True)
        while True:
            if self._try_create():
                self.acquired = True
                return self

            owner = self._read_owner()
            if owner is None:
                raise PrereleaseAlreadyRunningError(
                    "prerelease lock %s exists but has no valid owner record; "
                    "verify that no sweep is running before removing it" % self.path
                )
            if self._owner_is_running(owner):
                raise PrereleaseAlreadyRunningError(
                    "another prerelease sweep is already using %s "
                    "(PID %s on %s)"
                    % (
                        self.work_dir,
                        owner.get("pid", "unknown"),
                        owner.get("hostname", "unknown host"),
                    )
                )

            try:
                os.unlink(self.path)
            except FileNotFoundError:
                continue
            except OSError as error:
                raise PrereleaseAlreadyRunningError(
                    "stale prerelease lock %s could not be removed: %s"
                    % (self.path, error)
                ) from error

    def release(self):
        if not self.acquired:
            return
        owner = self._read_owner()
        if owner and owner.get("token") == self.owner["token"]:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
        self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.release()

    def _try_create(self) -> bool:
        candidate = "%s.%s.tmp" % (self.path, self.owner["token"])
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.owner, handle)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(candidate, self.path)
            except FileExistsError:
                return False
            return True
        finally:
            try:
                os.unlink(candidate)
            except FileNotFoundError:
                pass

    def _read_owner(self) -> dict | None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                owner = json.load(handle)
        except (OSError, ValueError, TypeError):
            return None
        return owner if isinstance(owner, dict) else None

    @staticmethod
    def _owner_is_running(owner: dict) -> bool:
        if owner.get("hostname") != socket.gethostname():
            # A shared work directory may be visible from another host; only
            # that host can safely prove its PID stale.
            return True
        try:
            pid = int(owner["pid"])
            expected_create_time = float(owner["process_create_time"])
            process = psutil.Process(pid)
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return False
            return abs(process.create_time() - expected_create_time) < 1.0
        except (
            KeyError,
            TypeError,
            ValueError,
            psutil.NoSuchProcess,
            psutil.ZombieProcess,
        ):
            return False
        except psutil.AccessDenied:
            # Failing closed is safer than deleting a live owner's lock.
            return True


def _drain(q: Queue, result: PassResult, verbose: bool) -> None:
    """Consume workflow signals until the process reports it has stopped."""
    while True:
        try:
            report = q.get(timeout=1.0)
        except queue_mod.Empty:
            return  # caller decides whether to keep waiting
        except (EOFError, OSError):
            return

        signal = report.signal_type
        if signal == WorkflowSignals.NODE_STARTED:
            result.nodes_started += 1
            if verbose:
                print("      > %s" % report.node_name, flush=True)
        elif signal == WorkflowSignals.NODE_COMPLETED:
            result.nodes_completed += 1
        elif signal == WorkflowSignals.NODE_ERROR:
            result.node_errors.append(
                {
                    "node": report.node_name,
                    "workflow": report.workflow_name,
                    "crash_file": report.crash_file,
                    "info": report.info,
                }
            )
            print("      ! FAILED %s" % report.node_name, flush=True)
        elif signal == WorkflowSignals.WORKFLOW_INSUFFICIENT_RESOURCES:
            result.insufficient_resources = True
            print("      ! a node needs more RAM than the budget allows", flush=True)
        elif signal == WorkflowSignals.WORKFLOW_STOP:
            raise _Finished


class _Finished(Exception):
    """Internal signal: the workflow process reported WORKFLOW_STOP."""


class _TimedOut(Exception):
    """Internal signal: the pass exceeded its wall-clock budget."""


#: Default per-pass wall-clock budget: generous enough for a full-accuracy
#: recon-all pass, tight enough that a hung node (see the SegmentEndocranium
#: hang this once caught) does not block the rest of the sweep overnight.
DEFAULT_TIMEOUT_SECONDS = 3 * 3600


def run_pass(
    pass_item,
    exam,
    work_dir: str,
    cores: int,
    ram_gb: float,
    slicer_path: str = "",
    verbose: bool = False,
    test_run: bool = True,
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> PassResult:
    """Build and execute one pass, returning its result.

    Parameters
    ----------
    timeout_seconds : float, optional
        Kill the pass and record it as failed if it runs longer than this
        (wall clock, from process start). ``None`` disables the timeout.
    """
    from swane.nipype_pipeline.MainWorkflow import MainWorkflow

    result = PassResult(
        name=pass_item.name,
        inputs=[str(i) for i in pass_item.inputs],
        values=dict(pass_item.values),
        downgrades=[list(d) for d in pass_item.downgrades],
    )

    if pass_item.skipped:
        result.status = "skipped"
        result.reason = pass_item.skip_reason
        return result

    started = time.time()
    try:
        subject_dir, global_config, subject_config, input_state_list = prepare_subject(
            pass_item,
            exam,
            work_dir,
            cores=cores,
            ram_gb=ram_gb,
            slicer_path=slicer_path,
        )
        result.subject_dir = subject_dir

        workflow = MainWorkflow(
            name=WORKFLOW_NAME,
            base_dir=subject_dir,
            global_config=global_config,
            subject_config=subject_config,
            dependency_manager=DependencyManager(),
            subject_input_state_list=input_state_list,
            test_run=test_run,
        )
    except Exception:
        result.status = "error"
        result.reason = "workflow construction failed:\n%s" % traceback.format_exc()
        result.seconds = time.time() - started
        return result

    # The import is local: WorkflowProcess pulls in the whole nipype execution
    # stack, which is pointless when only planning.
    from swane.workers.WorkflowProcess import WorkflowProcess

    signal_queue = Queue()
    process = WorkflowProcess(pass_item.name, workflow, signal_queue)
    process.start()
    workflow_stopped = False

    try:
        while True:
            try:
                _drain(signal_queue, result, verbose)
            except _Finished:
                workflow_stopped = True
                break
            if not process.is_alive():
                # The queue feeder may finish just after the process itself.
                # Give a final drain a chance to observe a legitimate stop.
                process.join(timeout=0)
                try:
                    _drain(signal_queue, result, verbose)
                except _Finished:
                    workflow_stopped = True
                break
            if timeout_seconds is not None and time.time() - started > timeout_seconds:
                raise _TimedOut
    except _TimedOut:
        result.status = "error"
        result.reason = "timed out after %s (limit %s); the workflow was killed" % (
            _human_time(time.time() - started),
            _human_time(timeout_seconds),
        )
        print("      ! TIMED OUT after %s" % _human_time(timeout_seconds), flush=True)
        process.stop_event.set()
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
        result.seconds = time.time() - started
        return result
    except KeyboardInterrupt:
        result.status = "error"
        result.reason = "interrupted by the user"
        process.stop_event.set()
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
        result.seconds = time.time() - started
        raise
    finally:
        process.join(timeout=60)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    result.seconds = time.time() - started
    if not workflow_stopped:
        result.status = "error"
        result.reason = (
            "workflow process died without WORKFLOW_STOP (exit code %s)"
            % process.exitcode
        )
    elif result.node_errors:
        result.status = "failed"
        failed_nodes = []
        for error in result.node_errors:
            node_name = error.get("node") or "unknown node"
            if node_name not in failed_nodes:
                failed_nodes.append(node_name)
        result.reason = "%d node(s) failed: %s" % (
            len(result.node_errors),
            ", ".join(failed_nodes[:5]),
        )
    elif result.nodes_completed == 0:
        result.status = "failed"
        result.reason = "no node completed; see the pass log"
    else:
        result.status = "completed"
    return result


# --------------------------------------------------------------------------- #
# Resumable sweep
# --------------------------------------------------------------------------- #
def _state_path(work_dir: str) -> str:
    return os.path.join(work_dir, STATE_FILE)


def load_state(work_dir: str) -> dict:
    path = _state_path(work_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return {}


def save_state(work_dir: str, state: dict) -> None:
    path = _state_path(work_dir)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp, path)


def run_sweep(
    plan: list,
    exam,
    work_dir: str,
    cores: int,
    ram_gb: float,
    slicer_path: str = "",
    resume: bool = True,
    verbose: bool = False,
    test_run: bool = True,
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
    on_pass_done=None,
    _work_dir_lock=None,
) -> list:
    """Run every planned pass in order, persisting progress as it goes.

    Parameters
    ----------
    resume : bool
        Reuse the *completed* passes already recorded in the work directory
        (skipped and failed passes are always re-evaluated / retried).
    test_run : bool
        Tweak heavy node parameters to speed up each workflow at the cost of
        accuracy, without overriding options the user has explicitly
        configured. Defaults to True since this sweep exists to be fast; pass
        False for full-accuracy passes.
    timeout_seconds : float, optional
        Per-pass wall-clock budget passed through to :func:`run_pass`; a pass
        that exceeds it is killed and recorded as failed rather than blocking
        the rest of the sweep. ``None`` disables it.
    on_pass_done : callable, optional
        Invoked with each :class:`PassResult` as soon as it is available, so a
        caller can report progress without waiting for the whole sweep.
    """
    if _work_dir_lock is None:
        with PrereleaseWorkDirLock(work_dir) as work_dir_lock:
            return run_sweep(
                plan,
                exam,
                work_dir,
                cores=cores,
                ram_gb=ram_gb,
                slicer_path=slicer_path,
                resume=resume,
                verbose=verbose,
                test_run=test_run,
                timeout_seconds=timeout_seconds,
                on_pass_done=on_pass_done,
                _work_dir_lock=work_dir_lock,
            )
    if (
        not isinstance(_work_dir_lock, PrereleaseWorkDirLock)
        or not _work_dir_lock.acquired
        or _work_dir_lock.work_dir != os.path.abspath(work_dir)
    ):
        raise ValueError("_work_dir_lock does not own this prerelease work directory")

    os.makedirs(work_dir, exist_ok=True)
    state = load_state(work_dir) if resume else {}
    results = []

    runnable = [p for p in plan if not p.skipped]
    print(
        "Running %d pass(es) sequentially in %s" % (len(runnable), work_dir), flush=True
    )
    _preload_antspynet(runnable)

    for index, pass_item in enumerate(plan, start=1):
        previous = state.get(pass_item.name)
        if previous and _reusable(previous, pass_item):
            result = PassResult(
                **{k: v for k, v in previous.items() if k in PassResult.__annotations__}
            )
            print(
                "[%2d/%2d] %-28s reused (%s)"
                % (index, len(plan), pass_item.name, result.status),
                flush=True,
            )
            results.append(result)
            if on_pass_done:
                on_pass_done(result)
            continue

        if pass_item.skipped:
            result = PassResult(
                name=pass_item.name,
                status="skipped",
                reason=pass_item.skip_reason,
                inputs=[str(i) for i in pass_item.inputs],
                values=dict(pass_item.values),
            )
            print(
                "[%2d/%2d] %-28s SKIPPED (%s)"
                % (index, len(plan), pass_item.name, result.reason),
                flush=True,
            )
        else:
            print(
                "[%2d/%2d] %-28s running..." % (index, len(plan), pass_item.name),
                flush=True,
            )
            result = run_pass(
                pass_item,
                exam,
                work_dir,
                cores=cores,
                ram_gb=ram_gb,
                slicer_path=slicer_path,
                verbose=verbose,
                test_run=test_run,
                timeout_seconds=timeout_seconds,
            )
            print(
                "         -> %s in %s (%d/%d nodes)"
                % (
                    result.status,
                    _human_time(result.seconds),
                    result.nodes_completed,
                    result.nodes_started,
                ),
                flush=True,
            )

        results.append(result)
        state[pass_item.name] = result.to_json()
        save_state(work_dir, state)
        if result.subject_dir:
            _write_pass_result(result)
        if on_pass_done:
            on_pass_done(result)

    return results


def _preload_antspynet(runnable: list) -> None:
    """Fetch the antspynet weights before the first pass, if any pass needs them.

    Left to the workflows the download happens inside a nipype worker, where
    concurrent nodes race for the same file and a node waiting on the network
    is indistinguishable from a node that hangs. A failure here is reported and
    not fatal: the sweep then fails on the pass that actually needed the
    weights, with that pass's own diagnostics.
    """
    if not any(p.values.get("deskull_engine") == "ANTSPYNET" for p in runnable):
        return
    from swane.tests.prerelease.antspynet_cache import preload_antspynet_models

    try:
        preload_antspynet_models()
    except Exception as error:  # noqa: BLE001 - reported, never fatal here
        print("  antspynet pre-cache failed (%s); continuing" % error, flush=True)


def _reusable(previous: dict, pass_item) -> bool:
    # Only a *completed* pass is reused on resume: it has real results worth
    # keeping. Everything else is re-evaluated against the CURRENT host and plan:
    #   * skipped -- whether it should still be skipped depends on the current
    #     capabilities/budget (more RAM, --with-reconall, ...), so an old skip is
    #     never cached; the loop re-skips it for free if it still cannot run.
    #     This is what lets the Synth passes run once the RAM budget is raised.
    #   * failed/error -- a failed pass has no valid results, and a fix may well
    #     have landed since it ran, so it is retried rather than kept failed.
    #     nipype's per-node cache means the retry resumes from the first failed
    #     node, so it is cheap.
    if previous.get("status") != "completed":
        return False
    # A "completed" record is only as good as the results it points to: if the
    # pass directory was since removed (by hand, by cleanup, ...), trusting the
    # stale record would silently skip re-running it forever -- the same class
    # of staleness check_pass() already applies when it can score the record.
    subject_dir = previous.get("subject_dir")
    if not subject_dir or not os.path.isdir(subject_dir):
        return False
    # A capability the plan gates on can appear or disappear between runs (the
    # Matlab runtime installed, more RAM, a GPU added/removed, ...), which
    # changes what build_plan() resolves this pass's axis values to (e.g.
    # hippo_amyg_labels false->true once freesurfer_matlab shows up). A
    # "completed" record from before that still reflects the OLD, downgraded
    # values, so blindly reusing it would silently keep the pass permanently
    # degraded even after the missing requirement is fixed. Re-run instead:
    # nipype's per-node cache in the same subject_dir means only the nodes
    # whose inputs actually changed (e.g. SegmentHA) run again.
    return previous.get("values") == dict(pass_item.values)


def _write_pass_result(result: PassResult) -> None:
    try:
        with open(os.path.join(result.subject_dir, PASS_RESULT_FILE), "w") as handle:
            json.dump(result.to_json(), handle, indent=2)
    except OSError:
        pass


def _human_time(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm%02ds" % (seconds // 60, seconds % 60)
    return "%dh%02dm" % (seconds // 3600, (seconds % 3600) // 60)
