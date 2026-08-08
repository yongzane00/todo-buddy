# Cat animation sprite sheets

Each PNG in this folder is one animation state for the companion cat in
`src/todo_buddy/ui/cat_widget.py`:

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

All five sheets come from one grid image, `_source/Animated_kumquat.jpeg`
(five labeled rows in AWAKE_IDLE / SLEEPING / HAPPY / ANGRY / WAKE_UP order,
six frames per row). The build tool separates the sprite from the background,
strips the row labels, resamples onto a true pixel grid at one shared scale,
and palette-snaps every pixel:

```
pip install -e ".[tools]"
python tools/build_cat_sheet.py Animated_kumquat.jpeg --grid
```

Add `--preview` to also write ignored `_preview_<NAME>.png` review images at
6x. To swap in new art, replace the grid image (any name works — pass it to
`--grid`) and rebuild; row labels are stripped automatically because they
contain no orange. The tool also has a legacy per-state mode
(`python tools/build_cat_sheet.py <NAME> [--glyph z|heart|anger]`) that reads
`_source/<NAME>.png` single-row renders; the old renders it consumed now live
only in git history. To add a new state, add a row to the grid (and its name
to `GRID_ROWS` in the tool), then map the state to the filename in
`_SPRITE_FILES` in `cat_widget.py`.
