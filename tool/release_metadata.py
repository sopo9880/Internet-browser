#!/usr/bin/env python3
"""Strict, reproducible 0.x release metadata for Flutter + Android.

The Android versionCode is derived from the semantic version rather than the
number of CI runs, ensuring it increases when the app version increases.
"""
import argparse
import os
from pathlib import Path
import re
from typing import NamedTuple


class ReleaseMetadata(NamedTuple):
    version: str
    tag: str
    build_number: int
    version_code: int


_VERSION = re.compile(
    r"^version:\s*(0\.([0-9]+)\.([0-9]+))\+([0-9]+)\s*$",
    flags=re.MULTILINE,
)


def parse_pubspec(source: str) -> ReleaseMetadata:
    matches = list(_VERSION.finditer(source))
    if len(matches) != 1:
        raise ValueError("pubspec.yaml must have exactly one 0.x.y+build version")
    match = matches[0]
    version = match.group(1)
    minor, patch, build = (int(match.group(i)) for i in (2, 3, 4))
    if not (0 <= minor <= 2099 and 0 <= patch <= 999 and 1 <= build <= 999):
        raise ValueError("0.x.y+build requires minor<=2099, patch<=999, 1<=build<=999")
    version_code = minor * 1_000_000 + patch * 1_000 + build
    if version_code > 2_100_000_000:
        raise ValueError("Android versionCode exceeds supported release range")
    return ReleaseMetadata(version, f"v{version}", build, version_code)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pubspec", default="pubspec.yaml")
    parser.add_argument(
        "--github-output", default=os.environ.get("GITHUB_OUTPUT", "")
    )
    args = parser.parse_args()
    info = parse_pubspec(Path(args.pubspec).read_text(encoding="utf-8"))
    print(
        f"Release metadata: {info.tag}, Android versionCode={info.version_code}"
    )
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as output:
            output.write(f"version={info.version}\n")
            output.write(f"tag={info.tag}\n")
            output.write(f"version_code={info.version_code}\n")


if __name__ == "__main__":
    main()
