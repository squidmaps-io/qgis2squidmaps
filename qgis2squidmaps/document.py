# -*- coding: utf-8 -*-
"""Assemble a squidmaps map document. No QGIS imports, so it's testable alone.

See https://squidmaps.io/docs/spec for the format.
"""

import json

from .styles import DEFAULT_COLOR, clamp, round_to, truncate, zoom_for_bounds

MAX_BODY_BYTES = 5 * 1024 * 1024   # ephemeral maps API request limit
CLAIM_MAX_FEATURES = 1000          # limit for adding a map to an account
CLAIM_MAX_FEATURE_BYTES = 1024 * 1024
MAX_LEGEND_ROWS = 50
MAX_LAT = 85.051129

BASEMAP_STYLES = ("light", "streets", "gray", "dark")


def squidmaps_basemap(style="light", opacity=1, labels=True):
    return {
        "type": "SQUIDMAPS",
        "style": style,
        "opacity": opacity,
        "labelVisibility": labels,
    }


def xyz_basemap(name, url, opacity=1, tms=False):
    return {
        "type": "XYZ",
        "name": truncate(name, 100) or "Tiles",
        "url": url,
        "opacity": round_to(clamp(opacity, 0, 1), 3),
        "tms": bool(tms),
    }


def legend_symbol(kind, props):
    """A LegendSymbol copying a feature's style, per the spec."""
    if kind == "point":
        return {
            "type": "circle",
            "fill": props.get("@fill", DEFAULT_COLOR),
            "radius": props.get("@radius", 8),
            "stroke": props.get("@stroke", "#FFFFFF"),
            "strokeWidth": props.get("@stroke-width", 2),
            "icon": props.get("@icon"),
            "iconColor": props.get("@icon-color"),
        }
    symbol = {
        "type": "line" if kind == "line" else "area",
        "color": props.get("@line-color", DEFAULT_COLOR),
        "width": props.get("@line-width", 3 if kind == "line" else 2),
        "opacity": props.get("@line-opacity", 1),
        "dasharray": props.get("@line-dasharray", []),
        "cap": props.get("@line-cap", "round"),
    }
    if kind != "line":
        symbol["fillColor"] = props.get("@fill-color", DEFAULT_COLOR)
        symbol["fillOpacity"] = props.get("@fill-opacity", 0.3)
    return symbol


def clean_bounds(bounds):
    """[w, s, e, n] clamped to the spec's ranges, or None if unusable."""
    if not bounds:
        return None
    w, s, e, n = (float(v) for v in bounds)
    w, e = clamp(w, -180, 180), clamp(e, -180, 180)
    s, n = clamp(s, -MAX_LAT, MAX_LAT), clamp(n, -MAX_LAT, MAX_LAT)
    if not (w < e and s < n):
        return None
    return [round(w, 6), round(s, 6), round(e, 6), round(n, 6)]


def view_for_bounds(bounds):
    w, s, e, n = bounds
    return {
        "center": [round((w + e) / 2, 6), round((s + n) / 2, 6)],
        "zoom": zoom_for_bounds(bounds),
    }


def build_document(features, name, description="", basemap=None,
                   legend_rows=None, legend_title="Legend",
                   initial_bounds=None, restrict_bounds=None,
                   min_zoom=0, max_zoom=22, feature_list=True, search=False):
    """The whole map document.

    initial_bounds: [w, s, e, n] the map opens on, or None to fit features.
    restrict_bounds: [w, s, e, n] visitors can't pan out of, or None.
    """
    initial = clean_bounds(initial_bounds)
    restrict = clean_bounds(restrict_bounds)
    min_zoom = clamp(min_zoom, 0, 22)
    max_zoom = clamp(max_zoom, 0, 22)
    if min_zoom >= max_zoom:
        min_zoom, max_zoom = 0, 22

    legend = None
    if legend_rows:
        legend = {
            "title": truncate(legend_title, 100),
            "rows": legend_rows[:MAX_LEGEND_ROWS],
        }

    return {
        "name": truncate(name, 100) or "Untitled map",
        "description": truncate(description or "", 100000),
        "basemap": basemap,
        "extent": {
            "zoom": {"mode": "range", "min": min_zoom, "max": max_zoom},
            "bounds": restrict,
            "initialBounds": initial,
        },
        "view": view_for_bounds(initial) if initial else None,
        "legend": legend,
        "panel": {"featureList": bool(feature_list), "search": bool(search)},
        "features": features,
    }


def to_json(document, indent=None):
    return json.dumps(document, ensure_ascii=False, indent=indent,
                      separators=None if indent else (",", ":"))


def size_warnings(document):
    """Human-readable problems with sending or keeping the map, if any."""
    warnings = []
    body = len(to_json(document).encode("utf-8"))
    if body > MAX_BODY_BYTES:
        warnings.append(
            "The map is {:.1f} MB; the squidmaps API accepts at most 5 MB. "
            "Export fewer layers, only features in the current view, or "
            "simplify geometries.".format(body / 1024.0 / 1024.0))
    n = len(document.get("features", []))
    feature_bytes = len(to_json(document.get("features", [])).encode("utf-8"))
    if n > CLAIM_MAX_FEATURES or feature_bytes > CLAIM_MAX_FEATURE_BYTES:
        warnings.append(
            "The map has {} features ({:.1f} MB). It will open, but adding it "
            "to a squidmaps account is limited to 1,000 features and 1 MB of "
            "features per map.".format(n, feature_bytes / 1024.0 / 1024.0))
    return warnings
