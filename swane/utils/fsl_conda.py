"""Resolve the minimal FSL conda install SWANe needs.

Stdlib only, so it runs before SWANe is installed. It picks the **oldest FSL
release SWANe supports** (``DependencyManager.MIN_FSL_VERSION``) that FSL
publishes for the host platform, reads that release's environment file from
FSL's own release manifest, and pins the few FSL packages the SWANe workflows
call to the versions of that release. Raising ``MIN_FSL_VERSION`` therefore
moves every install that uses this module with it (CI runners and the installer).

FSL is downloaded from FSL's own conda channel on the host; nothing of it is
copied into this repository.

Usage::

    python swane/utils/fsl_conda.py [--platform macos-M1]
        [--release 6.0.7.9] [--format github|text]

``--format github`` prints ``release=...``, ``platform=...`` and ``specs=...``
lines for ``$GITHUB_OUTPUT``.
"""

import argparse
import json
import os
import platform as platform_mod
import re
import sys
import urllib.request

MANIFEST_URL = "https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/releases/manifest.json"
FSL_CHANNEL = "https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/public/"
DEPENDENCY_MANAGER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "DependencyManager.py"
)

#: The FSL packages SWANe runs, each with the commands it is installed for.
#: Their own dependencies (fsl-base, fsl-avwutils, fsl-fugue for applywarp and
#: convertwarp, fsl-fast4, fsl-melodic for melodic and fsl_regfilt) come in
#: through the solver. No CUDA package: none is built for macOS, and the CPU
#: commands cover every engine.
FSL_PACKAGES = (
    "fsl-bet2",  # bet
    "fsl-flirt",  # flirt, convert_xfm
    "fsl-fnirt",  # fnirt, invwarp
    "fsl-mcflirt",  # mcflirt
    "fsl-susan",  # susan
    "fsl-slicetimer",  # slicetimer
    "fsl-feat5",  # feat_model
    "fsl-film",  # film_gls
    "fsl-cluster",  # fsl-cluster, smoothest
    "fsl-eddy",  # eddy_cpu
    "fsl-fdt",  # eddy_correct, dtifit, bedpostx
    "fsl-ptx2",  # probtrackx2
    "fsl-xtract_data",  # XTRACT protocols under $FSLDIR/data/xtract_data
    # $FSLDIR/data/standard MNI152 images: SWANe reads its own templates from
    # TemplateFlow, but bet itself reads these for -A (betsurf) and -B
    # (standard_space_roi).
    "fsl-data_standard",
)
#: Pinned too, so the FSL Python scripts run on the interpreter of the release.
EXTRA_PACKAGES = ("python",)


def host_platform() -> str:
    """The FSL manifest name of the platform this script runs on."""
    machine = platform_mod.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "macos-M1" if arm else "macos-64"
    if sys.platform.startswith("linux"):
        return "linux-aarch64" if arm else "linux-64"
    raise SystemExit("FSL publishes no release for %s" % sys.platform)


def version_key(text: str):
    """Numeric sort key of an FSL release ('6.0.6.3'), or None if not one."""
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


def min_fsl_version(path: str = DEPENDENCY_MANAGER) -> str:
    """Read ``MIN_FSL_VERSION`` from the source, without importing SWANe."""
    with open(path, encoding="utf-8") as handle:
        match = re.search(r'MIN_FSL_VERSION\s*=\s*"([^"]+)"', handle.read())
    if match is None:
        raise SystemExit("MIN_FSL_VERSION not found in %s" % path)
    return match.group(1)


def read_text(location: str) -> str:
    """Read an http(s) URL or a local file."""
    if location.startswith(("http://", "https://")):
        with urllib.request.urlopen(location, timeout=60) as response:
            return response.read().decode("utf-8")
    with open(location, encoding="utf-8") as handle:
        return handle.read()


def select_release(manifest: dict, platform: str, minimum: str, release=None):
    """Return ``(release, environment_location)``.

    Without ``release``, the oldest release not older than ``minimum`` that
    has a build for ``platform``.
    """
    versions = manifest["versions"]
    if release is not None:
        candidates = [release] if release in versions else []
    else:
        floor = version_key(minimum)
        candidates = sorted(
            (v for v in versions if version_key(v) and version_key(v) >= floor),
            key=version_key,
        )
    for candidate in candidates:
        for build in versions[candidate]:
            if build.get("platform") == platform:
                return candidate, build["environment"]
    raise SystemExit(
        "no FSL release %s for platform %s in the manifest"
        % (release or ">= %s" % minimum, platform)
    )


def pinned_specs(environment: str, packages=FSL_PACKAGES + EXTRA_PACKAGES) -> list:
    """Conda specs ``name=version`` for ``packages``, from an environment file.

    FSL's release environment files list one ``- name version`` per line.
    """
    found = {}
    for line in environment.splitlines():
        match = re.match(r"^\s*-\s*([A-Za-z0-9_.-]+)\s+(\S+)\s*$", line)
        if match:
            found[match.group(1)] = match.group(2)
    missing = [name for name in packages if name not in found]
    if missing:
        raise SystemExit("the FSL release environment lacks: %s" % ", ".join(missing))
    return ["%s=%s" % (name, found[name]) for name in packages]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform", default=None, help="default: this host")
    parser.add_argument("--release", default=None, help="default: the minimum")
    parser.add_argument("--manifest", default=MANIFEST_URL)
    parser.add_argument("--format", choices=("text", "github"), default="text")
    args = parser.parse_args(argv)

    platform = args.platform or host_platform()
    manifest = json.loads(read_text(args.manifest))
    release, environment = select_release(
        manifest, platform, min_fsl_version(), args.release or None
    )
    specs = pinned_specs(read_text(environment))
    if args.format == "github":
        print("release=%s" % release)
        print("platform=%s" % platform)
        print("specs=%s" % " ".join(specs))
    else:
        print("FSL %s (%s)" % (release, platform))
        for spec in specs:
            print("  " + spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
