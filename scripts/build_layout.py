#!/usr/bin/env python3
"""Build the exact spritesheet guide image and coordinate manifest.

The plan JSON is authored by the skill after deciding actions and frame semantics.
This script is the source of truth for all frame rectangles.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

# GPT Image generation targets documented by OpenAI.
SUPPORTED_CANVASES: tuple[tuple[int, int], ...] = (
    (1024, 1024),
    (1536, 1024),
    (1024, 1536),
)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "action"


def partition(total: int, count: int) -> list[int]:
    """Split total pixels into count integer pieces that exactly sum to total."""
    if total <= 0:
        raise ValueError("total must be > 0")
    if count <= 0:
        raise ValueError("count must be > 0")
    base, remainder = divmod(total, count)
    return [base + (1 if i < remainder else 0) for i in range(count)]


def validate_plan(plan: dict[str, Any]) -> None:
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("plan.actions must be a non-empty list")

    canvas = plan.get("canvas")
    if canvas is not None:
        if not isinstance(canvas, dict):
            raise ValueError("plan.canvas must be an object when provided")
        if canvas.get("mode") == "auto":
            if set(canvas) != {"mode"}:
                raise ValueError('canvas {"mode":"auto"} cannot contain other fields')
        else:
            width = canvas.get("width")
            height = canvas.get("height")
            if not isinstance(width, int) or not isinstance(height, int):
                raise ValueError("canvas must be auto or contain integer width and height")
            if (width, height) not in SUPPORTED_CANVASES:
                supported = ", ".join(f"{w}x{h}" for w, h in SUPPORTED_CANVASES)
                raise ValueError(f"unsupported ImageGen canvas {width}x{height}; use one of: {supported}")

    seen: set[str] = set()
    for action in actions:
        name = action.get("name")
        frames = action.get("frames")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("every action needs a non-empty name")
        action_id = action.get("id") or slugify(name)
        if action_id in seen:
            raise ValueError(f"duplicate action id: {action_id}")
        seen.add(action_id)
        if not isinstance(frames, list) or not frames:
            raise ValueError(f"action {action_id} must contain at least one frame")
        for index, frame in enumerate(frames):
            if not isinstance(frame.get("description"), str) or not frame["description"].strip():
                raise ValueError(f"action {action_id}, frame {index} needs a description")


def canvas_score(width: int, height: int, actions: list[dict[str, Any]]) -> tuple[float, float, int, int]:
    """Score a supported canvas for this action/frame geometry.

    Priority:
    1. maximize the smallest short side among every frame;
    2. prefer frame rectangles closer to square;
    3. prefer more total pixels;
    4. prefer a square canvas only as a final tie-breaker.
    """
    row_heights = partition(height, len(actions))
    frame_sizes: list[tuple[int, int]] = []
    for action, row_h in zip(actions, row_heights):
        for frame_w in partition(width, len(action["frames"])):
            frame_sizes.append((frame_w, row_h))

    min_short_side = min(min(frame_w, frame_h) for frame_w, frame_h in frame_sizes)
    shape_penalty = sum(abs(math.log(frame_w / frame_h)) for frame_w, frame_h in frame_sizes) / len(frame_sizes)
    return (
        float(min_short_side),
        -shape_penalty,
        width * height,
        1 if width == height else 0,
    )


def choose_canvas(actions: list[dict[str, Any]]) -> tuple[int, int]:
    """Pick the ImageGen-supported canvas that best fits the planned frames."""
    return max(SUPPORTED_CANVASES, key=lambda size: canvas_score(size[0], size[1], actions))


def resolve_canvas(plan: dict[str, Any]) -> tuple[int, int]:
    canvas = plan.get("canvas")
    if canvas is None or canvas.get("mode") == "auto":
        return choose_canvas(plan["actions"])
    return int(canvas["width"]), int(canvas["height"])


def build_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    validate_plan(plan)
    width, height = resolve_canvas(plan)
    actions = plan["actions"]

    row_heights = partition(height, len(actions))
    manifest_actions: list[dict[str, Any]] = []
    y = 0

    for action_index, (action, row_h) in enumerate(zip(actions, row_heights)):
        action_id = action.get("id") or slugify(action["name"])
        frames = action["frames"]
        col_widths = partition(width, len(frames))
        x = 0
        manifest_frames: list[dict[str, Any]] = []

        for frame_index, (frame, frame_w) in enumerate(zip(frames, col_widths)):
            frame_id = frame.get("id") or f"{action_id}_{frame_index:02d}"
            manifest_frames.append(
                {
                    "id": frame_id,
                    "index": frame_index,
                    "x": x,
                    "y": y,
                    "w": frame_w,
                    "h": row_h,
                    "description": frame["description"],
                    "duration_ms": int(frame.get("duration_ms", action.get("duration_ms", 100))),
                }
            )
            x += frame_w

        manifest_actions.append(
            {
                "id": action_id,
                "name": action["name"],
                "description": action.get("description", ""),
                "row": action_index,
                "x": 0,
                "y": y,
                "w": width,
                "h": row_h,
                "loop": bool(action.get("loop", True)),
                "frames": manifest_frames,
            }
        )
        y += row_h

    return {
        "version": 1,
        "subject": plan.get("subject", ""),
        "style": plan.get("style", ""),
        "background": plan.get("background", "transparent preferred; otherwise solid neutral"),
        "layout": "rows_by_action",
        "canvas": {"width": width, "height": height},
        "actions": manifest_actions,
    }


def draw_guide(manifest: dict[str, Any], out_path: Path, line_width: int = 3) -> None:
    width = manifest["canvas"]["width"]
    height = manifest["canvas"]["height"]
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    # Draw each frame rectangle independently. Inclusive coordinates ensure the
    # outer edge is visible while x/y/w/h remain crop coordinates in the JSON.
    for action in manifest["actions"]:
        for frame in action["frames"]:
            x0, y0 = frame["x"], frame["y"]
            x1 = min(width - 1, x0 + frame["w"] - 1)
            y1 = min(height - 1, y0 + frame["h"] - 1)
            draw.rectangle([x0, y0, x1, y1], outline="black", width=line_width)

    image.save(out_path, "PNG")


def make_imagegen_prompt(manifest: dict[str, Any]) -> str:
    lines = [
        "Create a spritesheet by editing/filling the supplied guide image.",
        f"Target canvas: {manifest['canvas']['width']}x{manifest['canvas']['height']} pixels.",
        "This target was selected from the supported GPT Image output sizes.",
        "CRITICAL: keep every black guide box/divider in exactly the same location in the output.",
        "Do not add, remove, merge, resize, shift, curve, or redraw the boxes.",
        "Each frame must stay completely inside its own rectangle; never cross a divider.",
        "Keep subject identity, scale, camera, palette, rendering style, and lighting consistent across all frames.",
        "Use the same background treatment in every frame.",
        f"Subject: {manifest.get('subject', '')}",
        f"Style: {manifest.get('style', '')}",
        f"Background: {manifest.get('background', '')}",
        "Frame instructions follow. Coordinates are [x,y,w,h] from the top-left:",
    ]
    for action in manifest["actions"]:
        lines.append(f"ACTION {action['id']} ({action['name']}): {action.get('description', '')}")
        for frame in action["frames"]:
            lines.append(
                f"- {frame['id']} [{frame['x']},{frame['y']},{frame['w']},{frame['h']}]: {frame['description']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path, help="Input planning JSON")
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument("--line-width", type=int, default=3)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    manifest = build_manifest(plan)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "spritesheet.json"
    guide_path = args.out_dir / "layout_boxes.png"
    prompt_path = args.out_dir / "imagegen_prompt.txt"

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draw_guide(manifest, guide_path, max(1, args.line_width))
    prompt_path.write_text(make_imagegen_prompt(manifest), encoding="utf-8")

    print(f"canvas={manifest['canvas']['width']}x{manifest['canvas']['height']}")
    print(manifest_path)
    print(guide_path)
    print(prompt_path)


if __name__ == "__main__":
    main()
