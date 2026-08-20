# BILBO brand assets

Source file: [Figma](https://www.figma.com/design/9nhbTgYEPDlwRdMEj1VeHP/BILBO-logo-explorations)

Two marks, both built from the same lipid glyph: a round head and two tails.

| Variant | What it shows | Use |
|---|---|---|
| `bilayer` | Three lipids per leaflet, tails meeting at the centre, seen edge-on | Default. Reads as a membrane at any size |
| `grid` | Nine lipids seen from above, each at a different azimuthal angle | Alternate. Reads as the build step: lipids placed on a grid and rotated |

Wordmark is Archivo SemiBold, letter-spacing 2%, exported as outlines. No font is needed to render these files.

## Colour

Each colour carries four tones. `dark` is the wordmark on light backgrounds, `mid` is the mark on light backgrounds, `bright` is the mark on dark backgrounds, `light` is reserved for tints.

| Colour | dark | mid | bright | light |
|---|---|---|---|---|
| amber (primary) | `#633806` | `#BA7517` | `#EF9F27` | `#FAC775` |
| mustard | `#6E5308` | `#C9A227` | `#DBBD60` | `#F0DFA6` |
| gold | `#7A4B06` | `#EF9F27` | `#F4BA60` | `#FBDCA6` |
| rust | `#7A2E12` | `#B4451F` | `#CC7A5C` | `#E9BBA6` |
| olive | `#3A4A12` | `#6E8B22` | `#97AF5B` | `#C9DBA0` |
| coral | `#993C1D` | `#D85A30` | `#E58A6B` | `#F5C4B3` |
| green | `#27500A` | `#639922` | `#8DB857` | `#C0DD97` |
| teal | `#0F6E56` | `#1D9E75` | `#58BC9C` | `#9FE1CB` |
| cyan | `#0B4A5E` | `#1E8CA8` | `#5DB0C5` | `#A9DCE9` |
| blue | `#0C447C` | `#378ADD` | `#70ABE7` | `#B5D4F4` |
| indigo | `#2A2E6E` | `#4B54C4` | `#8188D7` | `#C3C7EE` |
| purple | `#3C3489` | `#7F77DD` | `#A39DE8` | `#CECBF6` |

Neutrals: ink `#1A1206`, cream `#FAEEDA`, gray mark `#7A7168`, gray word `#2E2A25`. The three-tone grayscale set is `#3F3B35`, `#7A7168`, `#A99F94`.

Twelve colours. The first six come from the previous kit; mustard, gold, rust, olive, indigo and cyan were added on request. The amber `bright` tone is the one the previous kit already used; every other `bright` is `mid` mixed 45% toward `light`.

## Forms

| Form | Content | PNG, bilayer | PNG, grid |
|---|---|---|---|
| `lockup` | mark left, BILBO right | 1776x592 | 1888x592 |
| `tagline` | mark left, BILBO over the expanded acronym | 2168x688 | 2296x688 |
| `stacked` | mark above, BILBO below | 1116x1132 | 1116x1132 |
| `symbol` | mark alone | 536x656 | 656x656 |

PNG is exported at 4x with a transparent background. SVG carries no background either.

## Treatments

| Treatment | Mark | Word | For |
|---|---|---|---|
| `color` | amber mid | amber dark | light backgrounds |
| `color-dark` | amber bright | cream | dark backgrounds |
| `black` | ink | ink | single-colour print, stamps, engraving |
| `white` | white | white | over photographs and solid colour |
| `gray` | gray mark | gray word | documents where colour would compete |

## Colour combinations

A membrane is a mixture, and the two leaflets need not have the same composition. These files colour the mark lipid by lipid.

| Combination | Rule |
|---|---|
| `duo-amber-teal`, `duo-amber-blue`, `duo-amber-coral`, `duo-teal-purple`, `duo-mustard-teal`, `duo-mustard-indigo`, `duo-mustard-rust`, `duo-gold-cyan`, `duo-olive-mustard` | Two species. In `bilayer` the upper leaflet takes the first colour and the lower leaflet the second, which is what an asymmetric bilayer looks like. In `grid` the two alternate across the lattice |
| `trio-amber-teal-coral`, `trio-amber-purple-green`, `trio-blue-coral-green`, `trio-mustard-rust-olive`, `trio-mustard-teal-indigo`, `trio-gold-coral-cyan` | Three species, one per column in `bilayer`, cycled across the lattice in `grid` |
| `spectrum`, `spectrum-warm`, `spectrum-cool` | Six colours, one per lipid. `warm` runs mustard to olive, `cool` runs teal to green |
| `grayscale-multi` | Three grays, the print fallback for any of the above |

Every combination also exists with the `-dark` suffix, retoned for dark backgrounds with a cream wordmark.

## Files

```
assets/brand/
  <variant>/                  amber and neutrals, svg and png, plus the cards with a background
  <variant>/colors/           the five non-amber colours, svg
  <variant>/combos/           per-lipid combinations, svg, png for spectrum and two others
  _base/                      the six exports from Figma, the only handwritten input
  generate.py                 rebuilds every file above from _base
  preview.py                  rebuilds the two contact sheets
```

File names read `bilbo-<form>-<variant>-<treatment>.<ext>`, for example `bilbo-lockup-bilayer-color.svg` or `bilbo-symbol-grid-spectrum-dark.svg`.

Cards that carry a background: `bilbo-lockup-<variant>-on-white|on-amber|on-ink.png` at 2400x800, and `bilbo-icon-<variant>-on-white|on-amber|on-ink.png` at 1024x1024, the second set sized for favicons and avatars.

The repository README uses `grid/bilbo-lockup-grid-on-amber.png`; the web app uses `grid/bilbo-lockup-grid-color.svg`.

Contact sheets, three per variant:

| Sheet | Shows |
|---|---|
| `preview-<variant>-forms.png` | the four forms in all five treatments |
| `preview-<variant>-colors.png` | all twelve colours, on light and on dark, plus the symbols in a row |
| `preview-<variant>-combos.png` | all nineteen per-lipid combinations, on light and on dark |

## Regenerating

`_base/` holds six SVGs exported from Figma, each carrying exactly two colours: `#BA7517` on every mark shape and `#633806` on every word shape. Everything else is a recolour.

```bash
cd assets/brand
python3 generate.py
python3 preview.py
```

The site serves its own copies. After regenerating, refresh them:

```bash
cp grid/bilbo-lockup-grid-color.svg ../../web/static/bilbo-logotype.svg
cp grid/bilbo-symbol-grid-color.svg ../../web/static/bilbo-icon.svg
```

Requires `rsvg-convert` and ImageMagick. Editing the geometry means editing the Figma file and replacing `_base/`, not editing the generated files.

## Rules

`lockup` is the default. `tagline` is for the first appearance in a document or page, where the acronym still needs expanding. `stacked` is for square and narrow spaces. `symbol` is for avatars, favicons, and anywhere the name is already present.

Clear space is half the height of the mark on every side. Below 120 px wide, drop the lockup and use the symbol.

Do not place a `color` file on a dark background: use `color-dark`. Do not recolour a file by hand; add the colour to `generate.py` so every form gets it.
