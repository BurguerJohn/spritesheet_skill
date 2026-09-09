#!/usr/bin/env python3
"""Use FFmpeg + spritesheet.json to crop frames and build one GIF per action."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise SystemExit("ffmpeg was not found on PATH")
    return executable


def validate_sheet_dimensions(ffmpeg: str, sheet: Path, manifest: dict[str, Any]) -> None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(sheet),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = result.stdout.strip()
    expected = f"{manifest['canvas']['width']}x{manifest['canvas']['height']}"
    if actual != expected:
        raise SystemExit(f"generated sheet has size {actual}, expected {expected}; coordinates would be invalid")


def crop_frame(ffmpeg: str, sheet: Path, frame: dict[str, Any], out_path: Path) -> None:
    crop = f"crop={frame['w']}:{frame['h']}:{frame['x']}:{frame['y']}"
    run([ffmpeg, "-y", "-i", str(sheet), "-vf", crop, "-frames:v", "1", "-update", "1", str(out_path)])


def build_gif(ffmpeg: str, frame_paths: list[Path], durations_ms: list[int], out_path: Path, loop: bool) -> None:
    # Concat demuxer supports per-frame duration while preserving exact crop dimensions.
    concat_path = out_path.with_suffix(".concat.txt")
    lines: list[str] = []
    for path, duration_ms in zip(frame_paths, durations_ms):
        safe = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe}'")
        lines.append(f"duration {max(1, duration_ms) / 1000:.6f}")
    # Repeat the final frame because concat ignores duration on the last entry.
    safe_last = str(frame_paths[-1].resolve()).replace("'", "'\\''")
    lines.append(f"file '{safe_last}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loop_value = "0" if loop else "-1"
    filter_complex = (
        "[0:v]split[a][b];"
        "[a]palettegen=stats_mode=full[p];"
        "[b][p]paletteuse=dither=sierra2_4a"
    )
    run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-filter_complex",
            filter_complex,
            "-loop",
            loop_value,
            str(out_path),
        ]
    )
    concat_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path, help="ImageGen output spritesheet PNG")
    parser.add_argument("manifest", type=Path, help="spritesheet.json")
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    ffmpeg = require_ffmpeg()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_sheet_dimensions(ffmpeg, args.sheet, manifest)

    frames_root = args.out_dir / "frames"
    gifs_root = args.out_dir / "gifs"
    frames_root.mkdir(parents=True, exist_ok=True)
    gifs_root.mkdir(parents=True, exist_ok=True)

    for action in manifest["actions"]:
        action_dir = frames_root / action["id"]
        action_dir.mkdir(parents=True, exist_ok=True)
        frame_paths: list[Path] = []
        durations: list[int] = []

        for frame in action["frames"]:
            frame_path = action_dir / f"{frame['index']:03d}_{frame['id']}.png"
            crop_frame(ffmpeg, args.sheet, frame, frame_path)
            frame_paths.append(frame_path)
            durations.append(int(frame.get("duration_ms", 100)))

        gif_path = gifs_root / f"{action['id']}.gif"
        build_gif(ffmpeg, frame_paths, durations, gif_path, bool(action.get("loop", True)))
        print(gif_path)


if __name__ == "__main__":
    main()
