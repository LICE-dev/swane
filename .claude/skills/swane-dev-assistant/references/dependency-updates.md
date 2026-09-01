# SWANe pip dependency updates

Read this reference before bumping a pinned dependency in `setup.py` (e.g. `nipype`, `numpy`, `nibabel`, `PySide6`, `pydicom`, `SimpleITK`) or before letting a loose one (`packaging`, `cryptography`) resolve to a new major/minor version.

## Why this needs care beyond `pip install -U`

- `swane/patches/nipype_patches.py` monkeypatches private/internal Nipype surface (`nipype.utils.profiler.ResourceMonitor.__init__`, `nipype.pipeline.plugins.multiproc.run_node`) that is not part of Nipype's public API and can change silently between releases.
- Several dependencies are pinned to an exact version specifically to work around a known bug (e.g. `dcm2niix>=1.0.20241211,<=1.0.20260724`, commented in `setup.py`). Bumping the pin without re-checking the reason can reintroduce the bug or leave a now-unnecessary pin in place — this happened with `filelock<3.19`, a Nipype 1.10.0 workaround that was dropped when Nipype was bumped to 1.12.0.
- SWANe orchestrates a wide dependency graph (Nipype → networkx, traits, etc.; PySide6 → Qt; SimpleITK, nibabel, pydicom for image/DICOM I/O) where a transitive dependency can shift on its own and change behavior SWANe never pins directly.

## Procedure

1. **Read the target version's changelog/release notes**, not just the version diff. For a Nipype bump specifically, check whether `ResourceMonitor.__init__` or `pipeline.plugins.multiproc.run_node` changed signature, internal state, or removed the attributes `swane/patches/nipype_patches.py` relies on.
2. **Re-run every monkeypatch against the new version.** Import the patched module, call `apply_patches()`, and exercise the patched path (a resource-monitored workflow run) to confirm the redirected `.proc` file still lands in the configured `crashdump_dir`. A patch that stops raising but silently no-ops is the dangerous failure mode — assert on the actual file location, not just "no exception".
3. **Surface deprecated-API usage** introduced by the bump, across SWANe's own code and `swane/patches/`:
   ```bash
   python3 -W error::DeprecationWarning -m pytest swane/tests -m "not heavy"
   ```
   Treat any `DeprecationWarning` raised this way as a required follow-up, not noise to silence with a filter.
4. **Check the dependency's own dependencies recursively, not just the top-level package.** A `nipype` bump can shift its `networkx` or `traits` requirement, which can conflict with — or silently coexist with — an existing direct SWANe pin (`networkx==3.4.2`, `numpy==2.2.4`, `pydicom==3.0.1`). Inspect the new version's own `install_requires`/`pyproject.toml`, then:
   ```bash
   pip show <package>          # after install: Requires / Required-by
   pipdeptree -p <package>      # full recursive tree, if available in the dev environment
   ```
   A conflicting transitive pin fails loudly at install time; a *compatible* transitive bump does not, and is the one that needs deliberate checking.
5. **Check whether the reason for an existing pin still applies.** If a comment references a specific bug or version floor (the `swane_supplement>=0.1.2` TODO, the `dcm2niix` upper bound), verify against the new dependency's issue tracker/changelog whether the underlying bug is fixed upstream before loosening or removing the pin.
6. **Update `setup.py` deliberately**: exact pin (`==`) when a known bug or ABI-sensitive/monkeypatched behavior justifies it, a range otherwise. Comment a new exact pin the same way existing ones are commented, explaining why.
7. **Run the full validation ladder** from [testing.md](testing.md) after the bump — compileall, targeted tests, then the light suite at minimum; the heavy suite and `prerelease/` when the changed dependency touches workflow execution, image I/O, or GUI behavior. Validate on both Linux and macOS when the dependency has platform-specific wheels or behavior (Qt, SimpleITK, cryptography).

## Red flags requiring a stop-and-verify

- The bump touches `nipype`, `networkx`, or `traits` — anything `swane/patches/` reaches into.
- The new version's changelog mentions renamed/removed methods anywhere near the patched surface.
- `pip install` resolves a transitive dependency to a different version than before, without you having changed its pin.
- A `DeprecationWarning` appears in or near `swane/patches/` under the new version.
