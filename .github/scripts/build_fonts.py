#!/usr/bin/env python3
"""One-off: cut static Roboto Flex instances used by render_profile.py.

    python .github/scripts/build_fonts.py path/to/RobotoFlex[...].ttf

Writes assets/fonts/*.ttf (Latin subset, no hinting). The renderer embeds a per-SVG subset of
these, because an SVG shown through <img> cannot load web fonts.
"""

import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

OUT = Path(__file__).resolve().parents[2] / "assets" / "fonts"

INSTANCES = {
    "body": {"wght": 400, "opsz": 14},
    "medium": {"wght": 500, "opsz": 14},
    "bold": {"wght": 700, "opsz": 20},
    "display": {"wght": 450, "opsz": 72},
    "emph": {"wght": 900, "wdth": 120, "opsz": 72},
    "emph-title": {"wght": 760, "wdth": 110, "opsz": 28},
}

TEXT = "".join(chr(c) for c in range(0x20, 0x7F)) + "·—–↗▹×⇄…→★•’“”%"


def main(src: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, axes in INSTANCES.items():
        font = TTFont(src)
        pinned = {tag: None for tag in [a.axisTag for a in font["fvar"].axes]}
        pinned.update(axes)
        # Pin every axis: unspecified ones fall back to their default value.
        for axis in font["fvar"].axes:
            if pinned[axis.axisTag] is None:
                pinned[axis.axisTag] = axis.defaultValue
        static = instantiateVariableFont(font, pinned)
        opts = subset.Options()
        opts.hinting = False
        opts.layout_features = ["kern", "liga"]
        opts.name_IDs = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(text=TEXT)
        sub.subset(static)
        path = OUT / f"RobotoFlex-{name}.ttf"
        static.save(path)
        print(f"{path.name}: {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
