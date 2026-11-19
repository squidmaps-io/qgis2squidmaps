# -*- coding: utf-8 -*-
"""Pure-Python helpers for turning QGIS style values into squidmaps "@" values.

Nothing in this module imports QGIS, so it can be unit tested on its own.
QGIS-specific code (symbols.py) converts Qt/QGIS enums and units into the
plain values these functions take.
"""

import math
import re

# CSS pixels per millimetre (96 dpi), the unit squidmaps sizes are in.
PX_PER_MM = 96.0 / 25.4

DEFAULT_COLOR = "#3F80C4"

# Ranges from the squidmaps map spec.
CIRCLE_RADIUS = (2, 40)
CIRCLE_STROKE_WIDTH = (0, 10)
LINE_WIDTH = (0.5, 20)
LABEL_SIZE = (10, 24)
DASH_ITEM = (0, 100)
MAX_DASH_ITEMS = 8

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def round_to(value, digits=2):
    """Round, and drop a trailing .0 so the JSON stays tidy."""
    r = round(float(value), digits)
    return int(r) if r == int(r) else r


def hex_color(r, g, b):
    """'#RRGGBB' from 0-255 channels."""
    return "#{:02X}{:02X}{:02X}".format(
        int(clamp(r, 0, 255)), int(clamp(g, 0, 255)), int(clamp(b, 0, 255)))


def is_hex_color(value):
    return isinstance(value, str) and bool(_HEX_RE.match(value))


def opacity(*alphas):
    """Multiply 0-1 alphas together, e.g. color alpha x symbol x layer."""
    result = 1.0
    for a in alphas:
        if a is None:
            continue
        result *= clamp(float(a), 0.0, 1.0)
    return round_to(result, 3)


def circle_radius(diameter_px):
    """QGIS marker sizes are diameters; squidmaps circles take a radius."""
    return round_to(clamp(diameter_px / 2.0, *CIRCLE_RADIUS), 1)


def circle_stroke_width(width_px):
    return round_to(clamp(width_px, *CIRCLE_STROKE_WIDTH), 1)


def line_width(width_px):
    # QGIS treats a 0 width as a hairline, one device pixel wide.
    if width_px <= 0:
        width_px = 1
    return round_to(clamp(width_px, *LINE_WIDTH), 1)


def label_size(points):
    """QGIS label sizes are usually points; squidmaps wants pixels."""
    return round_to(clamp(points * 96.0 / 72.0, *LABEL_SIZE), 0)


# Qt's own dash patterns, in multiples of the pen width.
_QT_DASHES = {
    "dash": [4, 2],
    "dot": [1, 2],
    "dashdot": [4, 2, 1, 2],
    "dashdotdot": [4, 2, 1, 2, 1, 2],
}


def dasharray(pen_style, custom=None, width_px=None):
    """squidmaps @line-dasharray for a Qt pen style name.

    pen_style: 'solid', 'dash', 'dot', 'dashdot', 'dashdotdot', 'custom'
    custom: for 'custom', dash/gap lengths in pixels; divided by width_px,
            since squidmaps measures dashes in line widths.
    """
    if pen_style == "custom" and custom:
        w = width_px if width_px and width_px > 0 else 1
        pattern = [v / w for v in custom]
    else:
        pattern = list(_QT_DASHES.get(pen_style, []))
    if not pattern:
        return []
    # Qt and MapLibre both add caps to each dash, so the pattern carries
    # over as is.
    pattern = [round_to(clamp(v, *DASH_ITEM), 2)
               for v in pattern[:MAX_DASH_ITEMS]]
    if len(pattern) % 2:
        pattern = pattern[:-1]
    return pattern


def truncate(text, limit):
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|])")


def escape_markdown(text):
    """Escape characters that would turn attribute values into formatting."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def popup_markdown(rows):
    """Markdown for a feature's popup from (label, value) pairs.

    Values that are URLs become links; empty values are left out.
    """
    lines = []
    for label, value in rows:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if re.match(r"^https?://\S+$", text):
            shown = "[{}]({})".format(escape_markdown(text), text)
        else:
            # Keep line breaks inside a value.
            shown = "  \n".join(escape_markdown(t) for t in text.splitlines())
        lines.append("**{}**: {}".format(escape_markdown(label), shown))
    return "\n\n".join(lines)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text, fallback="layer"):
    s = _SLUG_RE.sub("-", str(text).lower()).strip("-")
    return s[:40] or fallback


def zoom_for_bounds(bounds, width_px=1200, height_px=800):
    """Web Mercator zoom at which bounds [w, s, e, n] fits a viewport."""
    w, s, e, n = bounds

    def merc_y(lat):
        lat = clamp(lat, -85.051129, 85.051129)
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    dx = max(abs(e - w) / 360.0, 1e-9)
    dy = max(abs(merc_y(n) - merc_y(s)) / (2 * math.pi), 1e-9)
    z = min(math.log2(width_px / 256.0 / dx), math.log2(height_px / 256.0 / dy))
    return round_to(clamp(z, 0, 22), 2)
