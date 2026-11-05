#!/usr/bin/env python3
"""Refresh the bundled fallback license copies from upstream.

Run before a release so swane/licenses/*.txt stays current. This only fetches
license *text* for display; it does not fetch or vendor any tool source code.
"""

import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from swane.utils.LicenseReference import LICENSES, bundled_license_path  # noqa: E402


def main() -> int:
    for tool_id, info in LICENSES.items():
        dest = bundled_license_path(info)
        print(f"Fetching {tool_id} license from {info.official_url}")
        with urllib.request.urlopen(info.official_url, timeout=30) as resp:
            data = resp.read()
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        print(f"  wrote {dest} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
