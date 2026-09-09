import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("extract_and_gif", ROOT / "scripts" / "extract_and_gif.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class ExportTests(unittest.TestCase):
    def test_auto_combined_layout_is_horizontal_up_to_four(self):
        self.assertEqual(mod.combined_layout(1), (1, 1))
        self.assertEqual(mod.combined_layout(4), (4, 1))

    def test_auto_combined_layout_becomes_compact_grid(self):
        self.assertEqual(mod.combined_layout(5), (3, 2))
        self.assertEqual(mod.combined_layout(8), (3, 3))

    def test_combined_layout_can_be_forced(self):
        self.assertEqual(mod.combined_layout(5, "horizontal"), (5, 1))
        self.assertEqual(mod.combined_layout(3, "grid"), (2, 2))

    def test_sync_plan_stretches_each_action_to_longest_duration(self):
        target, speeds, pts = mod.synchronization_plan([0.4, 0.8, 0.5])
        self.assertAlmostEqual(target, 0.8)
        self.assertEqual(speeds, [0.5, 1.0, 0.625])
        self.assertEqual(pts, [2.0, 1.0, 1.6])

    def test_gif_duration_quantizes_to_centiseconds(self):
        self.assertEqual(mod.quantize_gif_duration_ms(70), 70)
        self.assertEqual(mod.quantize_gif_duration_ms(75), 80)
        self.assertEqual(mod.quantize_gif_duration_ms(5), 20)

    def test_gif_duration_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            mod.quantize_gif_duration_ms(0)


if __name__ == "__main__":
    unittest.main()
