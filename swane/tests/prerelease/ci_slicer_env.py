"""Resolve the 3D Slicer package a CI runner installs.

Stdlib only, so it runs before SWANe is installed. It asks Slicer's own package
server (``slicer-packages.kitware.com``, the backend of download.slicer.org)
for the stable application package of a pinned Slicer release on the runner
OS, and prints its download URL, file name and SHA-512.

Slicer publishes macOS packages for ``amd64`` only: on Apple Silicon runners
it runs under Rosetta, exactly as it does on users' machines.

Slicer is downloaded from Kitware's server on the runner; nothing of it is
copied into this repository.

Usage::

    python swane/tests/prerelease/ci_slicer_env.py [--os macosx|win|linux]
        [--release 5.12.4] [--format github|text]

``--format github`` prints ``release=...``, ``os=...``, ``url=...``,
``filename=...`` and ``sha512=...`` lines for ``$GITHUB_OUTPUT``.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

#: The Slicer release CI installs by default: a recent stable one, pinned so a
#: new Slicer release never changes a run silently. Bump it deliberately.
DEFAULT_RELEASE = "5.12.4"
#: Slicer publishes macOS packages for amd64 only (see the module docstring).
ARCH = "amd64"

SERVER = "https://slicer-packages.kitware.com/api/v1"
#: The "Slicer" application id on the package server.
APP_ID = "5f4474d0e1d8c75dfc705482"


def host_os() -> str:
    """The package server name of the OS this script runs on."""
    if sys.platform == "darwin":
        return "macosx"
    if sys.platform == "win32":
        return "win"
    if sys.platform.startswith("linux"):
        return "linux"
    raise SystemExit("Slicer publishes no package for %s" % sys.platform)


def read_json(url: str):
    """GET ``url`` and decode its JSON body."""
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def packages_url(release: str, os_name: str) -> str:
    """The query listing the application packages of ``release`` on ``os_name``."""
    query = urllib.parse.urlencode(
        {"release_id_or_name": release, "os": os_name, "arch": ARCH, "limit": 50}
    )
    return "%s/app/%s/package?%s" % (SERVER, APP_ID, query)


def select_package(packages: list, release: str, os_name: str) -> dict:
    """The stable package of ``release`` for ``os_name``/``ARCH``.

    The server filters already; matching again here keeps a loose server-side
    filter from installing a preview build or another platform.
    """
    for package in packages:
        meta = package.get("meta", {})
        if (
            meta.get("os") == os_name
            and meta.get("arch") == ARCH
            and meta.get("release") == release
            and not meta.get("pre_release", False)
        ):
            return package
    raise SystemExit("no stable Slicer %s package for %s-%s" % (release, os_name, ARCH))


def select_file(files: list, os_name: str) -> dict:
    """The installer file of a package item (``.exe``/``.dmg``/``.tar.gz``)."""
    suffix = {"win": ".exe", "macosx": ".dmg", "linux": ".tar.gz"}[os_name]
    for entry in files:
        if entry.get("name", "").endswith(suffix):
            return entry
    raise SystemExit("the Slicer package has no %s file" % suffix)


def resolve(release: str, os_name: str, fetch=read_json) -> dict:
    """Everything the install step needs to download and verify the package."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", release):
        raise SystemExit("not a Slicer release: %r" % release)
    package = select_package(fetch(packages_url(release, os_name)), release, os_name)
    item_id = package["_id"]
    entry = select_file(fetch("%s/item/%s/files" % (SERVER, item_id)), os_name)
    return {
        "release": release,
        "os": os_name,
        "url": "%s/item/%s/download" % (SERVER, item_id),
        "filename": entry["name"],
        "sha512": entry["sha512"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--os", dest="os_name", default=None, help="default: host")
    parser.add_argument("--release", default=None, help="default: %s" % DEFAULT_RELEASE)
    parser.add_argument("--format", choices=("text", "github"), default="text")
    args = parser.parse_args(argv)

    info = resolve(args.release or DEFAULT_RELEASE, args.os_name or host_os())
    if args.format == "github":
        for key in ("release", "os", "url", "filename", "sha512"):
            print("%s=%s" % (key, info[key]))
    else:
        print("Slicer %s (%s-%s)" % (info["release"], info["os"], ARCH))
        print("  %s" % info["filename"])
        print("  %s" % info["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
