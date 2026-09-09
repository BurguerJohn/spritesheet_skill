# spritesheet_skill

A ChatGPT skill for building deterministic spritesheets with **Pillow for geometry**, **ImageGen for artwork**, and **FFmpeg for extraction/animation**.

## Pipeline

```text
user request
    ↓
actions + frame semantics
    ↓
plan.json
    ↓
auto-select ImageGen-native canvas
    ├── 1024x1024
    ├── 1536x1024
    └── 1024x1536
    ↓
Python / Pillow
    ├── layout_boxes.png
    ├── spritesheet.json (x, y, w, h + frame descriptions)
    └── imagegen_prompt.txt
    ↓
ImageGen fills the exact guide boxes at the selected aspect/target size
    ↓
spritesheet_imagegen_raw.png
    ↓
Pillow normalization only if the ImageGen surface returns a different pixel size with the same aspect ratio
    ↓
spritesheet_generated.png
    ↓
FFmpeg crops using spritesheet.json
    ├── frames/<action>/*.png
    ├── gifs/<action>.gif
    ├── gifs/all_actions.gif
    └── gifs/all_actions.json
```

The critical rule is that **Pillow-generated geometry and `spritesheet.json` are the source of truth**. Image generation is not allowed to redefine the boxes.

## ImageGen-native canvas selection

By default, planning JSON should use:

```json
"canvas": {"mode": "auto"}
```

`build_layout.py` evaluates the supported generation targets `1024x1024`, `1536x1024`, and `1024x1536`. It selects the canvas that gives the planned frames the largest useful short side, then prefers frame shapes closer to square. This makes the choice depend on the actual number of action rows and frames per action instead of using a fixed square sheet.

An explicit canvas is accepted only when it is one of those supported targets.

## Synchronized combined GIF

After generating the GIF for every action, `extract_and_gif.py` also creates `gifs/all_actions.gif`.

The exporter measures the real duration of each generated GIF with FFprobe, uses the longest action as the shared cycle duration, and retimes every shorter action with FFmpeg `setpts`. Each source contributes exactly one cycle, so all actions reach their loop boundary at the same instant and restart together.

The combined layout is automatic:

- 1–4 actions: one horizontal row;
- 5+ actions: a compact near-square grid.

Use `--combined-layout horizontal` or `--combined-layout grid` to override the automatic choice. Actions are padded to a common cell size without scaling their pixels. `gifs/all_actions.json` records the source durations, target duration, layout, and playback-speed factor used for each action.

The composite loop is timing-perfect. Visual seamlessness still depends on the first and last poses of each action being authored as a seamless loop when `loop=true`.

## Requirements

- Python 3.10+
- Pillow
- FFmpeg + FFprobe on `PATH`
- an environment with ImageGen available for the artwork step

```bash
python -m pip install -r requirements.txt
```

## Example

Build the deterministic layout and manifest:

```bash
python scripts/build_layout.py examples/dog.plan.json --out-dir output
```

The included dog example has 3 actions with 4 frames each, so auto-selection chooses a landscape `1536x1024` generation canvas.

After using `output/layout_boxes.png` + `output/imagegen_prompt.txt` with ImageGen, save the untouched result as `output/spritesheet_imagegen_raw.png`, then normalize/verify it:

```bash
python scripts/normalize_sheet.py \
  output/spritesheet_imagegen_raw.png \
  output/spritesheet.json \
  output/spritesheet_generated.png
```

Then export frames, per-action GIFs, and the synchronized combined GIF:

```bash
python scripts/extract_and_gif.py \
  output/spritesheet_generated.png \
  output/spritesheet.json \
  --out-dir output
```

## Skill entrypoint

See [`SKILL.md`](SKILL.md).
