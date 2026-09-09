#!/usr/bin/env python3
"""Crop spritesheet frames, build variable-timing action GIFs, and a synchronized combined GIF."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

CHROMA_FFMPEG = "0xFF00FF"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def require_ffmpeg() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        raise SystemExit("ffmpeg was not found on PATH")
    if not ffprobe:
        raise SystemExit("ffprobe was not found on PATH")
    return ffmpeg, ffprobe


def probe_dimensions(ffprobe: str, path: Path) -> tuple[int, int]:
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
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    width, height = result.stdout.strip().split("x", 1)
    return int(width), int(height)


def probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit(f"could not determine a positive duration for {path}")
    return duration


def validate_sheet_dimensions(ffprobe: str, sheet: Path, manifest: dict[str, Any]) -> None:
    actual = probe_dimensions(ffprobe, sheet)
    expected = (int(manifest["canvas"]["width"]), int(manifest["canvas"]["height"]))
    if actual != expected:
        raise SystemExit(
            f"generated sheet has size {actual[0]}x{actual[1]}, "
            f"expected {expected[0]}x{expected[1]}; coordinates would be invalid"
        )


def crop_frame(ffmpeg: str, sheet: Path, frame: dict[str, Any], out_path: Path) -> None:
    crop = f"crop={frame['w']}:{frame['h']}:{frame['x']}:{frame['y']}"
    run([ffmpeg, "-loglevel", "error", "-y", "-i", str(sheet), "-vf", crop, "-frames:v", "1", "-update", "1", str(out_path)])


def pad_frame(ffmpeg: str, source: Path, width: int, height: int, out_path: Path) -> None:
    """Pad a cropped frame with chroma magenta, without scaling."""
    pad = f"pad={width}:{height}:0:0:color={CHROMA_FFMPEG}"
    run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            pad,
            "-frames:v",
            "1",
            "-update",
            "1",
            str(out_path),
        ]
    )


def build_gif(
    ffmpeg: str,
    frame_paths: list[Path],
    durations_ms: list[int],
    out_path: Path,
    loop: bool,
    frame_sizes: list[tuple[int, int]],
) -> None:
    if not frame_paths:
        raise ValueError("frame_paths must not be empty")
    if len(frame_paths) != len(durations_ms) or len(frame_paths) != len(frame_sizes):
        raise ValueError("frame paths, durations, and sizes must have matching lengths")
    if any(type(duration) is not int or duration <= 0 for duration in durations_ms):
        raise ValueError("every GIF frame needs a positive integer duration_ms")

    max_w = max(width for width, _ in frame_sizes)
    max_h = max(height for _, height in frame_sizes)

    with tempfile.TemporaryDirectory(prefix=f"{out_path.stem}_gif_frames_") as tmp:
        tmp_dir = Path(tmp)
        normalized_paths: list[Path] = []
        for index, (path, size) in enumerate(zip(frame_paths, frame_sizes)):
            if size == (max_w, max_h):
                normalized_paths.append(path)
                continue
            padded = tmp_dir / f"{index:04d}.png"
            pad_frame(ffmpeg, path, max_w, max_h, padded)
            normalized_paths.append(padded)

        concat_path = tmp_dir / "frames.concat.txt"
        lines: list[str] = []
        for path, duration_ms in zip(normalized_paths, durations_ms):
            safe = str(path.resolve()).replace("'", "'\\''")
            lines.append(f"file '{safe}'")
            lines.append(f"duration {duration_ms / 1000:.6f}")
        # Concat applies a duration to an entry only when another entry follows it.
        safe_last = str(normalized_paths[-1].resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe_last}'")
        concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        loop_value = "0" if loop else "-1"
        filter_complex = (
            "[0:v]fps=100,split[a][b];"
            "[a]palettegen=stats_mode=full[p];"
            "[b][p]paletteuse=dither=sierra2_4a"
        )
        run(
            [
                ffmpeg,
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-filter_complex",
                filter_complex,
                "-t",
                f"{sum(durations_ms) / 1000:.6f}",
                "-loop",
                loop_value,
                str(out_path),
            ]
        )


def combined_layout(action_count: int, mode: str = "auto") -> tuple[int, int]:
    if action_count <= 0:
        raise ValueError("action_count must be positive")
    if mode not in {"auto", "horizontal", "grid"}:
        raise ValueError("combined layout must be auto, horizontal, or grid")
    if mode == "horizontal" or (mode == "auto" and action_count <= 4):
        return action_count, 1
    columns = math.ceil(math.sqrt(action_count))
    rows = math.ceil(action_count / columns)
    return columns, rows


def synchronization_plan(durations: list[float]) -> tuple[float, list[float], list[float]]:
    """Return target duration, playback speeds, and PTS stretch factors."""
    if not durations or any((not math.isfinite(d) or d <= 0) for d in durations):
        raise ValueError("durations must contain positive finite values")
    target_duration = max(durations)
    playback_speeds = [duration / target_duration for duration in durations]
    pts_factors = [target_duration / duration for duration in durations]
    return target_duration, playback_speeds, pts_factors


def build_combined_gif(
    ffmpeg: str,
    ffprobe: str,
    gif_paths: list[Path],
    out_path: Path,
    layout_mode: str = "auto",
) -> dict[str, Any]:
    """Combine one cycle of every action GIF and retime them to end together."""
    if not gif_paths:
        raise ValueError("gif_paths must not be empty")

    durations = [probe_duration(ffprobe, path) for path in gif_paths]
    dimensions = [probe_dimensions(ffprobe, path) for path in gif_paths]
    target_duration, speed_factors, pts_factors = synchronization_plan(durations)
    # setpts factor is inverse playback speed: target / source.

    cell_w = max(width for width, _ in dimensions)
    cell_h = max(height for _, height in dimensions)
    columns, rows = combined_layout(len(gif_paths), layout_mode)

    cmd = [ffmpeg, "-loglevel", "error", "-y"]
    for path in gif_paths:
        # Ignore GIF loop metadata so exactly one source cycle is retimed.
        cmd.extend(["-ignore_loop", "1", "-i", str(path)])

    filters: list[str] = []
    labels: list[str] = []
    for index, factor in enumerate(pts_factors):
        label = f"v{index}"
        filters.append(
            f"[{index}:v]settb=AVTB,setpts=(PTS-STARTPTS)*{factor:.12f},"
            f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:color={CHROMA_FFMPEG},"
            f"tpad=stop_mode=clone:stop_duration={target_duration:.6f},"
            f"trim=duration={target_duration:.6f},fps=100[{label}]"
        )
        labels.append(f"[{label}]")

    if len(gif_paths) == 1:
        filters.append(f"{labels[0]}null[stacked]")
    elif rows == 1:
        filters.append("".join(labels) + f"hstack=inputs={len(gif_paths)}:shortest=1[stacked]")
    else:
        positions = []
        for index in range(len(gif_paths)):
            col = index % columns
            row = index // columns
            positions.append(f"{col * cell_w}_{row * cell_h}")
        filters.append(
            "".join(labels)
            + f"xstack=inputs={len(gif_paths)}:layout={'|'.join(positions)}:fill={CHROMA_FFMPEG}[stacked]"
        )

    filters.append(
        "[stacked]split[palette_source][gif_source];"
        "[palette_source]palettegen=stats_mode=full[palette];"
        "[gif_source][palette]paletteuse=dither=sierra2_4a[out]"
    )

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-t",
            f"{target_duration:.6f}",
            "-loop",
            "0",
            str(out_path),
        ]
    )
    run(cmd)

    return {
        "path": str(out_path),
        "layout": "horizontal" if rows == 1 else "grid",
        "columns": columns,
        "rows": rows,
        "cell": {"width": cell_w, "height": cell_h},
        "background": "#FF00FF",
        "target_duration_seconds": target_duration,
        "actions": [
            {
                "gif": str(path),
                "source_duration_seconds": duration,
                "playback_speed": speed,
            }
            for path, duration, speed in zip(gif_paths, durations, speed_factors)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path, help="ImageGen output spritesheet PNG")
    parser.add_argument("manifest", type=Path, help="spritesheet.json")
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--combined-layout",
        choices=["auto", "horizontal", "grid"],
        default="auto",
        help="layout for gifs/all_actions.gif; auto uses horizontal up to 4 actions, then a compact grid",
    )
    args = parser.parse_args()

    ffmpeg, ffprobe = require_ffmpeg()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_sheet_dimensions(ffprobe, args.sheet, manifest)

    frames_root = args.out_dir / "frames"
    gifs_root = args.out_dir / "gifs"
    frames_root.mkdir(parents=True, exist_ok=True)
    gifs_root.mkdir(parents=True, exist_ok=True)

    action_gifs: list[Path] = []
    for action in manifest["actions"]:
        action_dir = frames_root / action["id"]
        action_dir.mkdir(parents=True, exist_ok=True)
        frame_paths: list[Path] = []
        durations: list[int] = []
        frame_sizes: list[tuple[int, int]] = []

        for frame in action["frames"]:
            frame_path = action_dir / f"{frame['index']:03d}_{frame['id']}.png"
            crop_frame(ffmpeg, args.sheet, frame, frame_path)
            frame_paths.append(frame_path)
            durations.append(int(frame["duration_ms"]))
            frame_sizes.append((int(frame["w"]), int(frame["h"])))

        gif_path = gifs_root / f"{action['id']}.gif"
        build_gif(
            ffmpeg,
            frame_paths,
            durations,
            gif_path,
            bool(action.get("loop", True)),
            frame_sizes,
        )
        action_gifs.append(gif_path)
        print(gif_path)

    combined_path = gifs_root / "all_actions.gif"
    combined_meta = build_combined_gif(
        ffmpeg,
        ffprobe,
        action_gifs,
        combined_path,
        args.combined_layout,
    )
    metadata_path = gifs_root / "all_actions.json"
    metadata_path.write_text(json.dumps(combined_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(combined_path)
    print(metadata_path)


if __name__ == "__main__":
    main()
