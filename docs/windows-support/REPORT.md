# Windows support — final CI report (2026-10-05)

> Temporary working document, like the rest of `docs/windows-support/`.
> Full chronological log: `PROGRESS.md`. Branch: `claude/windows-support-7ukj50`
> (`claude/windows-support` was NOT updated; fast-forward it if needed).

## Outcome: HANDOFF §1 goal met, all on commit 322a0b2

| Suite | OS | Run |
|---|---|---|
| light | windows-latest | https://github.com/LICE-dev/swane/actions/runs/37339587776 |
| light | macos-latest | https://github.com/LICE-dev/swane/actions/runs/37339592511 |
| heavy | windows-latest | https://github.com/LICE-dev/swane/actions/runs/37339583284 |
| heavy | macos-latest | https://github.com/LICE-dev/swane/actions/runs/37339577992 |
| prerelease | windows-latest | https://github.com/LICE-dev/swane/actions/runs/37339597869 (attempt 2) |

Prerelease: 7/7 passes and `prerelease-summary` green; plan reports
"Coverage: every reachable axis value is exercised". Linux light (local,
Python 3.12): 1546 passed, 13 skipped; the two "known" dev failures did not
reproduce (the container needs the `en_US.utf8` locale for SWANe's FSL probe).

## Fixes

Product (Windows-only, Linux/macOS unchanged):
- `install_windows_io_makedirs` (`swane/patches/nipype_patches.py`,
  `windows_compat.WINDOWS_OS`): sibling DataSinks sharing `results/` raced on
  `os.makedirs`; nipype tolerates only the POSIX "File exists" message, so
  Windows failed with WinError 183. Tests: `swane/tests/patches/test_windows_io_makedirs.py`.

Prerelease/test infrastructure:
- phantom build `NameError` (`fs_home` → `freesurfer_home`);
- CI fetches/caches the HCP842 atlas so DTI/DIPY-tractography passes run on Windows;
- light/heavy run with `pytest-timeout` + faulthandler (a hang dumps stacks and fails);
- `rs_components` check expects `ic_dim` components when `ic_dim > 0`.

Tests:
- Slicer script snapshots normalise `repr()`-escaped Windows paths;
- dipy motion oracle root was hard-coded `/home/mau` → `~/test_swane/...`;
- dipy RecoBundles test used 4 OpenMP threads on the 3-core macOS runner (stall) → 2;
- matrix snapshots pin `ResourceManager.get_os_type` to "linux" (SynthSeg RAM is per-OS);
- UI conftest dummy `QRunnable` auto-deleted by the pool → heap corruption /
  segfault (9/24 runs) → `setAutoDelete(False)` (0/24);
- heavy ANTs tests: `dense_ants_affine` fixture (dense mean-squares affine +
  antspyx deterministic mode); stack negative control given a real margin.

## Rulings taken without the maintainer (cost if wrong)

- HCP842 atlas in CI: ~650 MB of Actions cache; FSL-host evidence unchanged.
- Matrix snapshots pinned to Linux RAM tables: a macOS-only RAM-table
  regression would not show in snapshots.
- Fixed-`ic_dim` ICA expectation = `ic_dim`: check does not apply on FSL hosts.
- Deterministic ANTs heavy tests: they no longer probe antspyx optimiser
  stability, only SWANe's transform bookkeeping.
- Test-harness issues fixed in tests, not product code; no stable contract and
  no FSL-host prerelease execution changed.

## Skips (legitimate)

- light: `fork` start method absent (Windows); FSL-only matrix snapshots;
  POSIX-only tests on Windows; Windows-shim tests on real Windows (installed at
  import); no BLAS info (macOS numpy).
- heavy: 3D Slicer not installed; dipy CSD oracle inputs only on the maintainer's box.
- prerelease: FSL, FreeSurfer/Synth tools, Slicer, CUDA absent; recon-all opt-in.

## Open items (product, not fixed)

- Intermittent native crash on Windows: "access violation" in antspyx
  `antsImageHeaderInfo` (`ants.image_read`, node `fa_2_ref_ants_apply`,
  pass `dti_tractography_dipy`), 1 in 5 runs; not reproduced, not root-caused.
- SWANe's own `QRunnable` workers use the same auto-delete pattern that
  corrupted the heap in tests; low risk (long-running) but worth a review.
- dipy RecoBundles/SLR with `num_threads` > cores stalls for minutes on macOS.
- `.claude/skills/swane-dev-assistant/references/testing.md` still outdated (HANDOFF §7).

## Still needs a real Windows machine

HANDOFF §8 (pythonw / `python -m swane` launch, wizard and home notice, full
FSL-free workflow, deleting a subject with its log open, non-admin without
symlinks, real 3D Slicer) plus the antspyx access violation above.
