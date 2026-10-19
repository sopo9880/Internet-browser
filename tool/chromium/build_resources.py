#!/usr/bin/env python3
"""Fail-closed resource limits for a Chromium source build on WSL2 or Linux.

WSL2 with 23 GiB RAM and 24 GiB swap may build Chromium with deliberately
limited parallelism. Swap is NOT a replacement for enough physical RAM.
This check validates capacity, not successful compilation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

MIN_DISK_KIB = 120_000_000
HIGH_RAM_KIB = 30_000_000
MIN_RAM_KIB = 20 * 1024 * 1024
MIN_SWAP_KIB = 16 * 1024 * 1024
MIN_COMBINED_KIB = 40 * 1024 * 1024
MIN_AVAILABLE_KIB = 12 * 1024 * 1024


def parse_meminfo(meminfo: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in meminfo.splitlines():
        match = re.fullmatch(r"(\w+):\s*(\d+)\s+kB\s*", line)
        if match:
            values[match.group(1)] = int(match.group(2))
    for key in ("MemTotal", "MemAvailable", "SwapTotal"):
        if key not in values:
            raise ValueError(f"Missing Linux memory statistic: {key}")
    return values


def validate_build_resources(
    meminfo: str, free_disk_bytes: int, ninja_jobs: int, sync_jobs: int,
) -> dict[str, int | str]:
    values = parse_meminfo(meminfo)
    ram = values["MemTotal"]
    available = values["MemAvailable"]
    swap = values["SwapTotal"]
    if free_disk_bytes < MIN_DISK_KIB * 1024:
        raise ValueError("Chromium needs at least ~120 GB free Linux filesystem space")
    if ram < MIN_RAM_KIB:
        raise ValueError("Chromium requires at least 20 GiB physical Linux RAM")
    if available < MIN_AVAILABLE_KIB:
        raise ValueError("Less than 12 GiB usable Linux memory is available; stop competing work")
    low_memory = ram < HIGH_RAM_KIB
    if low_memory:
        if swap < MIN_SWAP_KIB or ram + swap < MIN_COMBINED_KIB:
            raise ValueError(
                "WSL2 low-RAM Chromium mode requires at least 16 GiB swap "
                "and 40 GiB combined RAM+swap (23 GiB RAM + 24 GiB swap recommended)"
            )
        max_ninja, max_sync = 3, 2
        mode = "constrained-ram-with-swap"
    else:
        max_ninja, max_sync = 8, 4
        mode = "high-memory"
    if not (1 <= ninja_jobs <= max_ninja):
        raise ValueError(f"Chromium ninja jobs must be 1..{max_ninja} in {mode} mode")
    if not (1 <= sync_jobs <= max_sync):
        raise ValueError(f"Chromium gclient jobs must be 1..{max_sync} in {mode} mode")
    return {
        "mode": mode,
        "ram_gib": ram // (1024 * 1024),
        "available_gib": available // (1024 * 1024),
        "swap_gib": swap // (1024 * 1024),
        "disk_free_gib": free_disk_bytes // (1024**3),
        "ninja_jobs": ninja_jobs,
        "sync_jobs": sync_jobs,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--ninja-jobs", type=int, default=3)
    p.add_argument("--sync-jobs", type=int, default=2)
    args = p.parse_args()
    report = validate_build_resources(
        Path("/proc/meminfo").read_text(encoding="ascii"),
        shutil.disk_usage(args.workspace).free,
        args.ninja_jobs,
        args.sync_jobs,
    )
    for key, value in report.items():
        print(f"Chromium build preflight {key}: {value}")


if __name__ == "__main__":
    main()
