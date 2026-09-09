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
Python / Pillow
    ├── layout_boxes.png
    ├── spritesheet.json (x, y, w, h + frame descriptions)
    └── imagegen_prompt.txt
    ↓
ImageGen fills the exact guide boxes
    ↓
spritesheet_imagegen_raw.png
    ↓
Pillow normalizes to manifest resolution (same aspect ratio only)
    ↓
spritesheet_generated.png
    ↓
FFmpeg crops using spritesheet.json
    ├── frames/<action>/*.png
    └── gifs/<action>.gif
```

The critical rule is that **Pillow-generated geometry and `spritesheet.json` are the source of truth**. Image generation is not allowed to redefine the boxes.

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

After using `output/layout_boxes.png` + `output/imagegen_prompt.txt` with ImageGen, save the untouched result as `output/spritesheet_imagegen_raw.png`, then normalize it:

```bash
python scripts/normalize_sheet.py \
  output/spritesheet_imagegen_raw.png \
  output/spritesheet.json \
  output/spritesheet_generated.png
```

Then export frames and GIFs:

```bash
python scripts/extract_and_gif.py \
  output/spritesheet_generated.png \
  output/spritesheet.json \
  --out-dir output
```

## Skill entrypoint

See [`SKILL.md`](SKILL.md).
