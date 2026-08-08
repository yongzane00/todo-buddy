# Cat animation sprite sheets

Each PNG in this folder is one animation state for the companion cat in
`src/todo_companion/ui/cat_widget.py`:

| Sheet | State | Played when |
| --- | --- | --- |
| `AWAKE_IDLE.png` | awake | default; blinks and flicks its tail (220 ms/frame) |
| `SLEEPING.png` | sleeping | 20 s without activity (slow 620 ms/frame cycle) |
| `WAKE_UP.png` | waking | one-shot stretch when a sleeping cat is disturbed |
| `HAPPY.png` | happy | a quest is completed (1.8 s celebration) |
| `ANGRY.png` | angry | while the card header is being dragged |

## Format contract

The widget validates each sheet on load and silently falls back to the
original Qt-painted cat if a sheet is missing or malformed:

- height exactly 64 px; width a whole multiple of 64 (one 64x64 cell per frame,
  no padding); any frame count works — the widget derives it from the width
- fully transparent background, hard alpha (0 or 255 only), no anti-aliasing,
  glow, or shadow
- grounded frames rest on baseline row 55; the body is centered on x = 31.5
- colors come from the shared 8-color palette defined in
  `tools/build_cat_sheet.py`

## Regenerating

`_source/` holds the raw AI renders (1536x1024, grey background, glow). The
build tool masks out the background, resamples onto a true pixel grid,
palette-snaps every pixel, and re-stamps floating glyphs that don't survive
the downscale:

```
pip install -e ".[tools]"
python tools/build_cat_sheet.py AWAKE_IDLE
python tools/build_cat_sheet.py SLEEPING --glyph z
python tools/build_cat_sheet.py WAKE_UP  --align per-frame
python tools/build_cat_sheet.py HAPPY    --glyph heart --min-blob 25
python tools/build_cat_sheet.py ANGRY    --glyph anger --min-blob 12
```

Add `--preview` to any command to also write an ignored `_preview_<NAME>.png`
at 6x for review. To add a new state, drop a render in `_source/`, build it,
and map the state to the filename in `_SPRITE_FILES` in `cat_widget.py`.
