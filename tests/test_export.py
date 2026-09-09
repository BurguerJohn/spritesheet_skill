import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

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
        target, speeds, pts = mod.synchronization_plan([[100, 300], [200, 600], [500]])
        self.assertAlmostEqual(target, 0.8)
        self.assertEqual(speeds, [0.5, 1.0, 0.625])
        self.assertEqual(pts, [2.0, 1.0, 1.6])

    def test_sync_plan_rounds_target_up_to_full_50fps_tick(self):
        target, speeds, pts = mod.synchronization_plan([[70, 80], [5, 75]])
        self.assertAlmostEqual(target, 0.16)
        self.assertEqual(speeds, [0.15 / 0.16, 0.10 / 0.16])
        self.assertEqual(pts, [0.16 / 0.15, 0.16 / 0.10])

    def test_sync_plan_rejects_missing_or_invalid_frame_holds(self):
        for durations in ([], [[]], [[0]], [[True]], [[1.5]]):
            with self.subTest(durations=durations), self.assertRaises(ValueError):
                mod.synchronization_plan(durations)

    def test_gif_duration_quantizes_to_centiseconds(self):
        self.assertEqual(mod.quantize_gif_duration_ms(70), 70)
        self.assertEqual(mod.quantize_gif_duration_ms(75), 80)
        self.assertEqual(mod.quantize_gif_duration_ms(5), 20)

    def test_gif_duration_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            mod.quantize_gif_duration_ms(0)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class GifIntegrationTests(unittest.TestCase):
    def inspect_gif(self, path):
        with Image.open(path) as image:
            self.assertEqual(image.info.get("loop"), 0)
            delays, colors = [], []
            size = image.size
            for index in range(image.n_frames):
                image.seek(index)
                delays.append(image.info["duration"])
                colors.append(image.convert("RGB").getpixel((8, 8)))
            self.assertTrue(all(delay >= 20 and delay % 10 == 0 for delay in delays))
            return size, delays, colors

    def test_cli_preserves_holds_and_encodes_browser_safe_infinite_loops(self):
        # An odd-centisecond cycle checks the last output hold. More than four
        # actions exercises grid padding; one action exercises the null stack.
        for count in (1, 2, 5):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                sheet = Image.new("RGB", (32, count * 16), "magenta")
                actions = []
                for i in range(count):
                    # Final action has one frame; action loop=false must still
                    # produce an infinitely repeating GIF preview.
                    holds = [70, 80] if i == 0 else ([100] if i == count - 1 else [20, 80])
                    frames = []
                    for j, hold in enumerate(holds):
                        sheet.paste("red" if j == 0 else "blue", (j * 16, i * 16, (j + 1) * 16, (i + 1) * 16))
                        frames.append({"id": f"a{i}_{j}", "index": j, "x": j * 16, "y": i * 16,
                                       "w": 16, "h": 16, "duration_ms": hold})
                    actions.append({"id": f"a{i}", "loop": False, "frames": frames})
                manifest = {"canvas": {"width": 32, "height": count * 16}, "actions": actions}
                sheet.save(root / "sheet.png")
                (root / "spritesheet.json").write_text(json.dumps(manifest))
                subprocess.run([sys.executable, str(ROOT / "scripts/extract_and_gif.py"),
                                str(root / "sheet.png"), str(root / "spritesheet.json"),
                                "--out-dir", str(root)], check=True, capture_output=True)
                for action in actions:
                    _, delays, _ = self.inspect_gif(root / "gifs" / f"{action['id']}.gif")
                    self.assertEqual(delays, [f["duration_ms"] for f in action["frames"]])
                size, delays, colors = self.inspect_gif(root / "gifs/all_actions.gif")
                self.assertEqual(sum(delays), 160)
                self.assertEqual(delays, [20] * 8)
                self.assertEqual(colors[:3], [(255, 0, 0)] * 3)
                self.assertEqual(colors[-3:], [(0, 0, 255)] * 3)
                cols, rows = mod.combined_layout(count)
                self.assertEqual(size, (cols * 16, rows * 16))
                metadata = json.loads((root / "gifs/all_actions.json").read_text())
                self.assertEqual(metadata["target_duration_seconds"], 0.16)
                self.assertEqual(metadata["actions"][0]["source_duration_seconds"], 0.15)
                self.assertEqual(metadata["fps"], 50)

    def test_combined_rejects_gif_timing_that_disagrees_with_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Image.new("RGB", (16, 16), "red").save(root / "frame.png")
            mod.build_gif("ffmpeg", [root / "frame.png"], [100], root / "action.gif", [(16, 16)])
            with self.assertRaisesRegex(ValueError, "does not match manifest"):
                mod.build_combined_gif("ffmpeg", "ffprobe", [root / "action.gif"],
                                       root / "all.gif", [[200]])


if __name__ == "__main__":
    unittest.main()
