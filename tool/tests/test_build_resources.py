"""Unit checks for constrained WSL2 Chromium source build preflight."""
import unittest

from tool.chromium.build_resources import validate_build_resources

GiB = 1024**3
MiB_KiB = 1024 * 1024


def meminfo(ram_gib: int, swap_gib: int, available_gib: int | None = None) -> str:
    available = ram_gib - 1 if available_gib is None else available_gib
    return (
        f"MemTotal: {ram_gib * MiB_KiB} kB\n"
        f"MemAvailable: {available * MiB_KiB} kB\n"
        f"SwapTotal: {swap_gib * MiB_KiB} kB\n"
    )


class ChromiumBuildResourceTests(unittest.TestCase):
    def test_user_wsl2_23_gib_ram_24_gib_swap_12_cpu(self):
        report = validate_build_resources(meminfo(23, 24, 22), 954 * GiB, 3, 2)
        self.assertEqual(report["mode"], "constrained-ram-with-swap")
        self.assertEqual(report["ram_gib"], 23)
        self.assertEqual(report["ninja_jobs"], 3)
        self.assertEqual(report["sync_jobs"], 2)

    def test_original_32_gib_ram_still_supported(self):
        report = validate_build_resources(meminfo(32, 0), 200 * GiB, 6, 4)
        self.assertEqual(report["mode"], "high-memory")

    def test_refuse_15_gib_ram_even_with_swap(self):
        with self.assertRaisesRegex(ValueError, "20 GiB"):
            validate_build_resources(meminfo(15, 24), 200 * GiB, 2, 2)

    def test_refuse_low_ram_without_enough_swap(self):
        for ram, swap in [(23, 0), (23, 8), (20, 16)]:
            with self.subTest(ram=ram, swap=swap), self.assertRaisesRegex(
                ValueError, "combined RAM\\+swap"
            ):
                validate_build_resources(meminfo(ram, swap), 200 * GiB, 3, 2)

    def test_refuse_overcommitted_build_workers(self):
        for ninja, sync in [(4, 2), (3, 3), (0, 2)]:
            with self.subTest(ninja=ninja, sync=sync), self.assertRaises(ValueError):
                validate_build_resources(meminfo(23, 24), 200 * GiB, ninja, sync)

    def test_refuse_insufficient_free_memory_or_disk(self):
        with self.assertRaisesRegex(ValueError, "usable Linux memory"):
            validate_build_resources(meminfo(23, 24, 6), 200 * GiB, 3, 2)
        with self.assertRaisesRegex(ValueError, "120 GB"):
            validate_build_resources(meminfo(23, 24), 90 * GiB, 3, 2)

    def test_reject_missing_linux_memory_stats(self):
        with self.assertRaisesRegex(ValueError, "MemAvailable"):
            validate_build_resources("MemTotal: 24117248 kB\n", 200 * GiB, 3, 2)


if __name__ == "__main__":
    unittest.main()
