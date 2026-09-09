import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_layout", ROOT / "scripts" / "build_layout.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


def make_actions(action_count: int, frames_per_action: int):
    return [
        {
            "name": f"action_{a}",
            "frames": [
                {"description": f"frame_{i}", "duration_ms": 100}
                for i in range(frames_per_action)
            ],
        }
        for a in range(action_count)
    ]


class LayoutTests(unittest.TestCase):
    def test_partition_is_exact(self):
        self.assertEqual(sum(mod.partition(512, 3)), 512)
        self.assertEqual(mod.partition(512, 4), [128, 128, 128, 128])

    def test_auto_canvas_prefers_landscape_for_more_frames_than_rows(self):
        self.assertEqual(mod.choose_canvas(make_actions(3, 4)), (1536, 1024))

    def test_auto_canvas_prefers_square_for_balanced_grid(self):
        self.assertEqual(mod.choose_canvas(make_actions(4, 4)), (1024, 1024))

    def test_auto_canvas_prefers_portrait_for_more_rows_than_frames(self):
        self.assertEqual(mod.choose_canvas(make_actions(6, 4)), (1024, 1536))

    def test_unsupported_explicit_canvas_is_rejected(self):
        plan = {
            "canvas": {"width": 512, "height": 512},
            "actions": make_actions(2, 2),
        }
        with self.assertRaises(ValueError):
            mod.build_manifest(plan)

    def test_frame_duration_is_required(self):
        plan = {
            "canvas": {"width": 1024, "height": 1024},
            "actions": [{"name": "a", "frames": [{"description": "missing timing"}]}],
        }
        with self.assertRaises(ValueError):
            mod.build_manifest(plan)

    def test_non_magenta_background_is_rejected(self):
        plan = {
            "background": "#FFFFFF",
            "canvas": {"width": 1024, "height": 1024},
            "actions": make_actions(1, 1),
        }
        with self.assertRaises(ValueError):
            mod.build_manifest(plan)

    def test_rows_fill_canvas_without_overlap_or_gaps(self):
        plan = {
            "canvas": {"width": 1024, "height": 1024},
            "actions": [
                {
                    "name": "a",
                    "frames": [{"description": str(i), "duration_ms": 100} for i in range(4)],
                },
                {
                    "name": "b",
                    "frames": [{"description": str(i), "duration_ms": 120} for i in range(3)],
                },
            ],
        }
        manifest = mod.build_manifest(plan)
        self.assertEqual(manifest["background"], "#FF00FF")
        self.assertEqual([a["h"] for a in manifest["actions"]], [512, 512])
        self.assertEqual([f["w"] for f in manifest["actions"][0]["frames"]], [256] * 4)
        self.assertEqual(sum(f["w"] for f in manifest["actions"][1]["frames"]), 1024)
        self.assertEqual(manifest["actions"][1]["y"], 512)
        self.assertEqual(manifest["actions"][1]["frames"][0]["duration_ms"], 120)

    def test_guide_uses_magenta_background_and_frame_y_coordinate(self):
        from PIL import Image
        import tempfile

        plan = {
            "canvas": {"width": 1024, "height": 1024},
            "actions": [
                {
                    "name": "top",
                    "frames": [
                        {"description": "a", "duration_ms": 100},
                        {"description": "b", "duration_ms": 100},
                    ],
                },
                {"name": "bottom", "frames": [{"description": "c", "duration_ms": 100}]},
            ],
        }
        manifest = mod.build_manifest(plan)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "guide.png"
            mod.draw_guide(manifest, path, line_width=1)
            image = Image.open(path)
            self.assertEqual(image.getpixel((512, 1023)), (0, 0, 0))
            self.assertEqual(image.getpixel((512, 768)), (255, 0, 255))


if __name__ == "__main__":
    unittest.main()
