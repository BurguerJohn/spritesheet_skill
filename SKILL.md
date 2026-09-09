---
name: spritesheet-builder
description: Plan, generate, slice, and animate spritesheets from a subject request. Use when the user asks for a spritesheet, sprite animation sheet, animation frames, or per-action GIFs.
---

# Spritesheet Builder

Create deterministic spritesheet layouts first, then use ImageGen only to fill those exact boxes. The Pillow-generated geometry and `spritesheet.json` are the source of truth for all crop coordinates.

## Required final outputs

Always return all of these artifacts:

1. `layout_boxes.png` — exact Pillow guide with all frame boxes.
2. `spritesheet_imagegen_raw.png` — raw ImageGen output, preserving the guide boxes.
3. `spritesheet_generated.png` — geometry-normalized PNG used for deterministic cropping.
4. `spritesheet.json` — action/frame manifest with exact `x`, `y`, `w`, `h` and frame descriptions.
5. `gifs/<action>.gif` — one animated GIF for every action.

Also keep `frames/<action>/*.png` when possible; these are useful intermediate exports.

## Workflow

### 1. Interpret the request

Identify the subject, requested art direction, requested actions, background requirements, animation timing, and any constraints.

If the user specifies actions, use them. If the user does not specify actions, choose a compact useful default set appropriate for the subject. Prefer 2–5 distinct actions rather than creating an excessively large sheet.

Examples of reasonable defaults:

- animal/character: idle, walk/run, sit/crouch, jump or reaction;
- vehicle: idle, move, turn, brake/impact;
- effect: appear, active/loop, dissipate;
- object/UI element: idle, activate, success, failure when semantically appropriate.

Do not invent actions that conflict with the subject or user intent.

### 2. Plan every frame before drawing anything

For each action:

- choose the frame count;
- define whether it loops;
- choose `duration_ms` per action or per frame;
- write a concrete visual description for every frame;
- make adjacent frame descriptions describe progressive motion, not unrelated poses;
- for looping actions, ensure the last frame transitions naturally back to the first.

Default guidance when the user gives no frame count:

- subtle idle: 3–4 frames;
- walk/run cycle: 4–8 frames;
- simple one-shot action: 3–6 frames;
- complex motion: 6–10 frames only when the extra frames materially help.

Create a planning JSON matching the shape of `examples/dog.plan.json`.

### 3. Choose an ImageGen-native canvas and create exact geometry with Pillow

The generation canvas must always be one of these GPT Image output targets:

- `1024x1024`
- `1536x1024`
- `1024x1536`

Unless the user explicitly chooses one of those supported sizes, set:

```json
"canvas": {"mode": "auto"}
```

The layout script scores all supported canvases after the actions and frame counts are known. It prioritizes:

1. maximizing the smallest short side of any frame box;
2. keeping frame boxes as close to square as practical;
3. using more total pixels when geometry is otherwise comparable.

This normally selects landscape for actions with many frames per row, portrait for many action rows, and square for balanced grids.

Run:

```bash
python scripts/build_layout.py plan.json --out-dir output
```

This creates:

- `output/layout_boxes.png`
- `output/spritesheet.json`
- `output/imagegen_prompt.txt`

Layout rule: one row per action, with that row split evenly across the action's frames. Integer remainder pixels are distributed deterministically so every row fills the canvas exactly with no gaps.

Never manually estimate coordinates after this step. Read them from `spritesheet.json`.

### 4. Feed the guide into ImageGen

Use `layout_boxes.png` as the input/reference image for ImageGen and use `imagegen_prompt.txt` plus the JSON semantics as the instructions.

Critical ImageGen constraints:

- request the exact target size selected in `spritesheet.json.canvas` whenever the ImageGen surface exposes an exact size control;
- preserve the guide aspect ratio and box geometry;
- preserve every black guide border/divider in the exact same position;
- never merge, remove, move, bend, resize, or redraw boxes;
- each frame's art must remain completely inside its own rectangle;
- keep subject identity, proportions, camera, scale, palette, lighting, and rendering style consistent;
- maintain a consistent background across frames;
- each frame must visually implement the specific description for its exact JSON rectangle;
- avoid text, labels, numbers, or annotations unless the user explicitly asks for them.

Save the untouched result as `output/spritesheet_imagegen_raw.png`.

The normal path is now to generate at the same dimensions used by Pillow, so no resize should be necessary. However, some ImageGen surfaces may still return a different pixel resolution while preserving aspect ratio. Keep the normalization step only as a fallback:

```bash
python scripts/normalize_sheet.py \
  output/spritesheet_imagegen_raw.png \
  output/spritesheet.json \
  output/spritesheet_generated.png
```

If the raw image already matches the manifest dimensions, this should preserve it without a geometry-changing resize. If the raw output differs, normalization is allowed only when it has exactly the same aspect ratio as the manifest. Never stretch a different aspect ratio. If the guide lines moved or warped, regenerate instead of pretending the coordinates still match.

### 5. Extract every frame and create per-action GIFs with FFmpeg

Run:

```bash
python scripts/extract_and_gif.py \
  output/spritesheet_generated.png \
  output/spritesheet.json \
  --out-dir output
```

The script uses FFmpeg crop filters with the exact JSON coordinates, exports PNG frames, and builds one palette-optimized GIF for each action.

Do not replace the JSON crop coordinates with visual guesses.

### 6. Validate and return artifacts

Before answering:

- verify `layout_boxes.png`, `spritesheet_imagegen_raw.png`, `spritesheet_generated.png`, and `spritesheet.json` exist;
- verify generated sheet dimensions equal `spritesheet.json.canvas`;
- verify every action has the expected number of extracted frame PNGs;
- verify one GIF exists per action;
- visually inspect at least the guide and final spritesheet when tools allow;
- report any ImageGen inconsistency instead of pretending the animation is correct.

Return download links/references for the guide, raw ImageGen sheet, normalized sheet, JSON, and every GIF.

## JSON contract

`spritesheet.json` uses top-left pixel coordinates:

```json
{
  "canvas": {"width": 1536, "height": 1024},
  "actions": [
    {
      "id": "walk",
      "frames": [
        {
          "id": "walk_00",
          "index": 0,
          "x": 0,
          "y": 0,
          "w": 384,
          "h": 512,
          "description": "...",
          "duration_ms": 100
        }
      ]
    }
  ]
}
```

Coordinates are half-open crop rectangles conceptually: pixels from `x` through `x+w-1`, and `y` through `y+h-1`.

## Design principles

- Geometry first, generation second.
- Use an ImageGen-native target size for the Pillow guide.
- JSON coordinates are authoritative.
- Motion continuity matters more than maximizing frame count.
- Keep sheets reasonably small so each frame has enough visual resolution.
- Prefer a simple background when the main goal is a game-ready sprite animation.
- If transparency is essential and ImageGen does not preserve it reliably, generate on a flat chroma/background and perform a deliberate post-processing step only when requested or clearly necessary.
