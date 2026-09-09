#!/usr/bin/env python3
"""Normalize an ImageGen result to the exact manifest canvas without changing aspect ratio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("imagegen_output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    target_w = int(manifest["canvas"]["width"])
    target_h = int(manifest["canvas"]["height"])

    with Image.open(args.imagegen_output) as image:
        source_w, source_h = image.size
        # Aspect ratio must match closely. Stretching a different aspect ratio would
        # invalidate the guide geometry even if the final pixel dimensions matched.
        source_ratio = source_w / source_h
        target_ratio = target_w / target_h
        if abs(source_ratio - target_ratio) > 1e-6:
            raise SystemExit(
                f"ImageGen output aspect ratio {source_w}x{source_h} does not match "
                f"manifest {target_w}x{target_h}; regenerate instead of stretching"
            )

        if (source_w, source_h) == (target_w, target_h):
            normalized = image.copy()
        else:
            normalized = image.resize((target_w, target_h), Image.Resampling.LANCZOS)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        normalized.save(args.output, "PNG")

    print(args.output)


if __name__ == "__main__":
    main()
