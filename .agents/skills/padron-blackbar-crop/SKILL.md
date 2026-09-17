---
name: padron-blackbar-crop
description: Use when detecting or cropping black bars, PRM blocks, dark borders, or burned-in letterbox from padrón/ID photos, when deciding a safe crop line near faces, or when crop QA quarantines an image
---

# padron-blackbar-crop

## Overview

Deterministic black-bar detection and cropping for registry (padrón) photos. Core principle: **the crop line is the top of the unwanted content minus margin — never "the first dark jump from the edge" and never a fixed % of the image.** Measured evidence (see `docs/research/sample-geometry.md`): the PRM block can start *inside* the photo (dark shoulder region 860–990 in the anchor) while real content (bright pixels) continues below the naive cut.

## When to use

- Photos with black bars/blocks containing white text ("PRM" or any siglas), on any side
- Deciding whether a dark side is a bar or legitimate dark content (clothes, shadow, vignette)
- Crop would touch bright/skin content → reduce cut or quarantine

## When NOT to use

- Image is uniformly dark (possible whole photo) → quarantine, never crop
- Image already clean → no-op, keep hash/dimensions identical
- Bar is added by the player/viewer (not burned-in pixels) → crop is wrong

## Detector cascade (order matters)

| Level | Detector | Cost | Decides |
|---|---|---|---|
| D0 | cached lot geometry (N samples agree, low stddev) | free | fast-path: reuse frozen geometry, recalibrate every K or on QA fail |
| D1 | row/column dark-fraction projection from edges | cheap | candidate crop lines per side |
| D2 | connected dark regions touching borders (mask grid) | cheap | confirms D1; catches L/C-shapes and corner blocks |
| D3 | bright-glyph anchor (luma>0.6, small area) inside dark zones | cheap | text top edge; OCR optional, position is enough |
| D4 | remote AI vision | OFF by default, `--allow-remote-ai`, test copies only | never replaces D0–D2 |

Accept a side only if: dark fill high (strict threshold 16/255), touches the border, no significant bright/skin pixels inside, **and** D1 and D2 agree. Disagreement → quarantine.

## Thresholds (defaults, calibrated on the anchor)

- strict dark: luma < 16/255; dark (JPEG noise): < 48/255; bright anchor: > 0.60
- margin above text top: 5 px (measured glyphs started y=1009, crop at y=1004)
- never crop into rows containing >0.5% bright pixels
- tune per lot; a fixed global threshold misclassifies dark clothing (measured: "left" side 84% dark-gray but 100% legit content)

## Common mistakes

| Mistake | Reality |
|---|---|
| Crop at first big dark jump from bottom | In the anchor that is y≈830 → destroys shoulder content |
| Fixed % crop or single side | Block can be L/C-shaped or mid-lower, not a border strip |
| One threshold for pure black only | JPEG noise / dark gray bars get missed (FFmpeg cropdetect lesson: bars are rarely pure black) |
| Trust "dark side = bar" | Anchor's left side is dark clothes; requires fill+border+no-bright+agreement |
| Re-encode with EXIF orientation kept | After crop+save, orientation tag 274 must be reset or pixels duplicate-rotate |
| Crop the only copy | Write to `out/`, source stays read-only |

## Red flags — stop and verify

- About to crop without measuring pixels first
- Face/bright region intersects candidate cut → quarantine instead
- Two detectors disagree beyond tolerance → quarantine, don't guess
- Status would be "ok" but bright pixels exist inside the removed area
