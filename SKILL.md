---
name: spritesheet-builder
description: Plan, generate, slice, and animate spritesheets from a subject request. Use when the user asks for a spritesheet, sprite animation sheet, animation frames, or per-action GIFs.
---

# Spritesheet Builder

Create deterministic spritesheet layouts first, then use ImageGen only to fill those exact boxes. The Pillow-generated geometry and `spritesheet.json` are the source of truth for all crop coordinates and frame timing.

The spritesheet background is always a flat chroma-key magenta: **`#FF00FF` / RGB(255, 0, 255)**. Do not substitute another background color.

## Required final outputs

Always return all of these artifacts:

1. `layout_boxes.png` — exact Pillow guide with all frame boxes on `#FF00FF`.
2. `spritesheet_imagegen_raw.png` — raw ImageGen output, preserving the guide boxes and magenta background.
3. `spritesheet_generated.png` — geometry-normalized PNG used for deterministic cropping.
4. `spritesheet.json` — action/frame manifest with exact `x`, `y`, `w`, `h`, `duration_ms`, and frame descriptions.
5. `gifs/<action>.gif` — one animated GIF for every action, honoring each frame's individual hold time.
6. `gifs/all_actions.gif` — synchronized preview containing every action, all reaching the loop boundary at the same instant.

Also keep `frames/<action>/*.png` when possible; these are useful intermediate exports. Keep `gifs/all_actions.json` as synchronization metadata.

## Workflow

### 1. Interpret the request

Identify the subject, requested art direction, requested actions, animation timing, and any constraints. The background does not need to be chosen: it is always `#FF00FF`.

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
- assign an explicit positive integer `duration_ms` to **every individual frame**;
- allow different frames in the same action to have different durations when the motion benefits from anticipation, impact, pause, recovery, or a held pose;
- write a concrete visual description for every frame;
- make adjacent frame descriptions describe progressive motion, not unrelated poses;
- for looping actions, ensure the last frame transitions naturally back to the first.

Never rely on one action-level duration as the timing source. The timing source of truth is `frame.duration_ms` in `spritesheet.json`.

Default guidance when the user gives no frame count:

- subtle idle: 3–4 frames;
- walk/run cycle: 4–8 frames;
- simple one-shot action: 3–6 frames;
- complex motion: 6–10 frames only when the extra frames materially help.

Timing guidance when the user gives no timing:

- quick transition/contact frame: roughly 60–120 ms;
- normal motion frame: roughly 90–180 ms;
- anticipation/recovery frame: roughly 120–220 ms;
- intentional hold or final pose: roughly 180–500 ms when appropriate.

GIF stores frame delays at centisecond granularity, so multiples of 10 ms are preferred when practical. Keep the requested/planned `duration_ms` in JSON even though final GIF timing may be quantized to the nearest representable delay.

Create a planning JSON matching the shape of `examples/dog.plan.json`. Always set:

```json
"background": "#FF00FF"
```

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

The Pillow guide itself must use a solid `#FF00FF` fill with black frame borders. Layout rule: one row per action, with that row split evenly across the action's frames. Integer remainder pixels are distributed deterministically so every row fills the canvas exactly with no gaps.

`build_layout.py` must reject plans that omit a frame's `duration_ms` or request a background other than `#FF00FF`.

Never manually estimate coordinates after this step. Read them from `spritesheet.json`.

### 4. Feed the guide into ImageGen

Use `layout_boxes.png` as the input/reference image for ImageGen and use `imagegen_prompt.txt` plus the JSON semantics as the instructions.

Critical ImageGen constraints:

- request the exact target size selected in `spritesheet.json.canvas` whenever the ImageGen surface exposes an exact size control;
- preserve the guide aspect ratio and box geometry;
- preserve every black guide border/divider in the exact same position;
- never merge, remove, move, bend, resize, or redraw boxes;
- each frame's art must remain completely inside its own rectangle;
- every frame background must remain one flat, uniform **`#FF00FF` / RGB(255,0,255)** field;
- do not add gradients, scenery, texture, shadows, lighting variation, or alternate colors to the background;
- avoid using the exact `#FF00FF` chroma color inside the sprite itself when possible;
- keep subject identity, proportions, camera, scale, palette, lighting, and rendering style consistent;
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

### 5. Extract every frame and create GIF outputs with FFmpeg

Run:

```bash
python scripts/extract_and_gif.py \
  output/spritesheet_generated.png \
  output/spritesheet.json \
  --out-dir output
```

The script uses FFmpeg crop filters with the exact JSON coordinates, exports PNG frames, and builds one palette-optimized GIF for each action.

FFmpeg supports a different hold time for every frame. The exporter uses the concat demuxer and writes a `duration` entry for each frame image based on that frame's `duration_ms`. For example, one action can legitimately use timings such as `80 ms, 80 ms, 140 ms, 300 ms` rather than one uniform delay.

If integer pixel remainders make frames in one action differ by 1 px, keep the exported crops exact and only pad temporary GIF inputs to the largest frame size. Never stretch or rescale individual action frames just to make FFmpeg concat accept them.

After all per-action GIFs exist, always create `gifs/all_actions.gif`:

1. measure the actual one-cycle duration of every action GIF with FFprobe;
2. choose the longest action duration as the target duration;
3. use exactly one cycle from every source GIF;
4. retime each shorter GIF with FFmpeg `setpts` so it ends at the same target timestamp as the longest GIF;
5. preserve each action's pixel size and only pad to a common cell size;
6. use a horizontal row for up to 4 actions and a compact near-square grid for 5 or more actions, unless the user explicitly requests horizontal or grid;
7. encode `all_actions.gif` with infinite looping so every action restarts at the same instant;
8. write `gifs/all_actions.json` containing source durations, target duration, layout, and playback-speed factors.

The playback speed for action `i` is:

```text
speed_i = source_duration_i / longest_duration
```

So a 0.4 s action next to a 0.8 s action runs at `0.5x`, while the 0.8 s action runs at `1.0x`; both finish at 0.8 s and restart together.

The combined file is timing-perfect. For a visually seamless boundary, any action marked `loop=true` must also have a first/last pose that was planned to loop seamlessly. Do not claim a one-shot action has a visually seamless boundary unless it actually does.

Do not replace the JSON crop coordinates with visual guesses.

### 6. Validate and return artifacts

Before answering:

- verify `layout_boxes.png`, `spritesheet_imagegen_raw.png`, `spritesheet_generated.png`, and `spritesheet.json` exist;
- verify `layout_boxes.png` and the generated spritesheet use `#FF00FF` as the empty background field;
- verify generated sheet dimensions equal `spritesheet.json.canvas`;
- verify every frame in the JSON contains a positive `duration_ms`;
- verify every action has the expected number of extracted frame PNGs;
- verify one GIF exists per action;
- verify per-action GIF timing follows each frame's `duration_ms`, subject to GIF delay quantization;
- verify `gifs/all_actions.gif` and `gifs/all_actions.json` exist;
- verify the combined GIF duration equals its synchronization target and every source action is retimed to that target;
- visually inspect at least the guide and final spritesheet when tools allow;
- report any ImageGen inconsistency instead of pretending the animation is correct.

Return download links/references for the guide, raw ImageGen sheet, normalized sheet, JSON, every action GIF, and the synchronized `all_actions.gif`.

## JSON contract

`spritesheet.json` uses top-left pixel coordinates. Every frame has its own explicit hold time:

```json
{
  "background": "#FF00FF",
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
          "description": "front paw reaches forward",
          "duration_ms": 90
        },
        {
          "id": "walk_01",
          "index": 1,
          "x": 384,
          "y": 0,
          "w": 384,
          "h": 512,
          "description": "passing pose",
          "duration_ms": 120
        }
      ]
    }
  ]
}
```

Coordinates are half-open crop rectangles conceptually: pixels from `x` through `x+w-1`, and `y` through `y+h-1`.

## Design principles

- Geometry first, generation second.
- The empty background is always exactly `#FF00FF`.
- Use an ImageGen-native target size for the Pillow guide.
- JSON coordinates and per-frame `duration_ms` are authoritative.
- Motion continuity matters more than maximizing frame count.
- Use variable frame timing when it improves animation rhythm.
- The combined preview must synchronize all action cycle boundaries.
- Keep sheets reasonably small so each frame has enough visual resolution.
