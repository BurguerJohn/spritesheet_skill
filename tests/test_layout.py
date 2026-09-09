import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_layout", ROOT / "scripts" / "build_layout.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class LayoutTests(unittest.TestCase):
    def test_partition_is_exact(self):
        self.assertEqual(sum(mod.partition(512, 3)), 512)
        self.assertEqual(mod.partition(512, 4), [128, 128, 128, 128])

    def test_rows_fill_canvas_without_overlap_or_gaps(self):
        plan = {
            "canvas": {"width": 512, "height": 512},
            "actions": [
                {"name": "a", "frames": [{"description": str(i)} for i in range(4)]},
                {"name": "b", "frames": [{"description": str(i)} for i in range(3)]},
            ],
        }
        manifest = mod.build_manifest(plan)
        self.assertEqual([a["h"] for a in manifest["actions"]], [256, 256])
        self.assertEqual([f["w"] for f in manifest["actions"][0]["frames"]], [128] * 4)
        self.assertEqual(sum(f["w"] for f in manifest["actions"][1]["frames"]), 512)
        self.assertEqual(manifest["actions"][1]["y"], 256)

    def test_guide_uses_frame_y_coordinate(self):
        from PIL import Image
        import tempfile

        plan = {
            "canvas": {"width": 300, "height": 200},
            "actions": [
                {"name": "top", "frames": [{"description": "a"}, {"description": "b"}]},
                {"name": "bottom", "frames": [{"description": "c"}]},
            ],
        }
        manifest = mod.build_manifest(plan)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "guide.png"
            mod.draw_guide(manifest, path, line_width=1)
            image = Image.open(path)
            # The second row starts at y=100 and its bottom border is y=199.
            self.assertEqual(image.getpixel((150, 199)), (0, 0, 0))
            self.assertEqual(image.getpixel((150, 150)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
