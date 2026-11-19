# -*- coding: utf-8 -*-
"""Convert QGIS symbols into squidmaps "@" style properties.

squidmaps styles each feature in its own properties, so instead of
translating whole renderers (as qgis2web does into JS) we ask the layer's
renderer which symbol it would draw each feature with and copy that symbol's
look. That covers single symbol, categorized, graduated, rule-based and
anything else QGIS can render.

squidmaps has a smaller vocabulary than QGIS: points are circles, lines are
one stroke, areas are a fill and an outline. Each symbol is reduced to its
closest equivalent: the first simple marker or fill, the top simple line.
"""

from qgis.core import (
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMapUnitScale,
    QgsMarkerSymbol,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSymbolLayer,
)

from . import styles

# Qt enum values, compared as ints so this works with PyQt5 and PyQt6.
_PEN_STYLES = {0: "none", 1: "solid", 2: "dash", 3: "dot", 4: "dashdot",
               5: "dashdotdot", 6: "custom"}
_CAP_STYLES = {0x00: "butt", 0x10: "square", 0x20: "round"}
_NO_BRUSH = 0


def enum_int(value):
    """An enum's int value under PyQt5 (ints) or PyQt6 (enum objects)."""
    return int(getattr(value, "value", value))


def geometry_kind(layer):
    """'point', 'line', 'polygon', or None for tables without geometry."""
    return {0: "point", 1: "line", 2: "polygon"}.get(
        enum_int(layer.geometryType()))


# --- units and data-defined values ------------------------------------------

def to_px(value, unit, context, map_unit_scale=None):
    """A length in a QGIS render unit, in CSS pixels.

    The render context's scale factor is fixed at 96 dpi (see
    make_render_context), so millimetres, points and inches convert the way a
    browser draws them, and map units use the current canvas scale.
    """
    try:
        return context.convertToPainterUnits(
            float(value), unit, map_unit_scale or QgsMapUnitScale())
    except Exception:
        return float(value) * styles.PX_PER_MM


def _property_key(name):
    """QgsSymbolLayer property key by name, for QGIS before and after 3.30."""
    scoped = getattr(QgsSymbolLayer, "Property", None)
    if scoped is not None and hasattr(scoped, name):
        return getattr(scoped, name)
    return getattr(QgsSymbolLayer, "Property" + name, None)


def _dd(symbol_layer, name, context, default, kind):
    """A symbol layer's data-defined value for the current feature, if set."""
    key = _property_key(name)
    if key is None:
        return default
    props = symbol_layer.dataDefinedProperties()
    try:
        if not props.isActive(key):
            return default
        exp_context = context.expressionContext()
        if kind == "color":
            result = props.valueAsColor(key, exp_context, default)
        else:
            result = props.valueAsDouble(key, exp_context, default)
    except Exception:
        return default
    # PyQGIS returns (value, ok) tuples for these.
    if isinstance(result, tuple):
        value, ok = result[0], result[-1]
        return value if ok and value is not None else default
    return result if result is not None else default


def _color(qcolor):
    return styles.hex_color(qcolor.red(), qcolor.green(), qcolor.blue())


def _alpha(qcolor):
    return qcolor.alphaF()


def _first(symbol, cls):
    for i in range(symbol.symbolLayerCount()):
        sl = symbol.symbolLayer(i)
        if sl.enabled() and isinstance(sl, cls):
            return sl
    return None


def _last(symbol, cls):
    for i in reversed(range(symbol.symbolLayerCount())):
        sl = symbol.symbolLayer(i)
        if sl.enabled() and isinstance(sl, cls):
            return sl
    return None


# --- symbols ------------------------------------------------------------------

def symbol_props(symbol, kind, context, layer_opacity=1.0):
    """squidmaps "@" properties for a QGIS symbol drawn as `kind`."""
    if symbol is None:
        return {}
    if kind == "point" and isinstance(symbol, QgsMarkerSymbol):
        return marker_props(symbol, context)
    if kind == "line" and isinstance(symbol, QgsLineSymbol):
        return line_props(symbol, context, symbol.opacity() * layer_opacity)
    if kind == "polygon" and isinstance(symbol, QgsFillSymbol):
        return fill_props(symbol, context, symbol.opacity() * layer_opacity)
    # Geometry generators and the like: fall back to the symbol's color.
    color = _color(symbol.color())
    if kind == "point":
        return {"@fill": color}
    if kind == "line":
        return {"@line-color": color}
    return {"@line-color": color, "@fill-color": color}


def marker_props(symbol, context):
    """A circle in the colors of the symbol's first marker layer.

    squidmaps points are circles, so marker shapes, SVGs and font markers
    become circles of the same color and size.
    """
    sl = _first(symbol, QgsSimpleMarkerSymbolLayer) or \
        (symbol.symbolLayer(0) if symbol.symbolLayerCount() else None)

    size = symbol.size()
    size_unit = symbol.sizeUnit()
    if sl is not None and hasattr(sl, "size"):
        size = _dd(sl, "Size", context, sl.size(), "double")
        size_unit = sl.sizeUnit()
    diameter = to_px(size, size_unit, context)

    fill = symbol.color()
    stroke = None
    stroke_px = 0.0
    if isinstance(sl, QgsSimpleMarkerSymbolLayer):
        fill = _dd(sl, "FillColor", context, sl.fillColor(), "color")
        if enum_int(sl.strokeStyle()) != 0:
            stroke = _dd(sl, "StrokeColor", context, sl.strokeColor(), "color")
            width = _dd(sl, "StrokeWidth", context, sl.strokeWidth(), "double")
            # A 0 width is a hairline in QGIS.
            stroke_px = max(1.0, to_px(width, sl.strokeWidthUnit(), context,
                                       sl.strokeWidthMapUnitScale()))
    elif sl is not None:
        fill = sl.color()

    props = {
        "@point-type": "circle",
        "@fill": _color(fill),
        "@radius": styles.circle_radius(diameter),
        "@stroke-width": styles.circle_stroke_width(stroke_px),
    }
    if stroke is not None and stroke.alpha() > 0:
        props["@stroke"] = _color(stroke)
    else:
        props["@stroke-width"] = 0
    return props


def _line_layer_props(sl, context, alpha):
    color = _dd(sl, "StrokeColor", context, sl.color(), "color")
    width = _dd(sl, "StrokeWidth", context, sl.width(), "double")
    width_px = to_px(width, sl.widthUnit(), context, sl.widthMapUnitScale())
    pen = _PEN_STYLES.get(enum_int(sl.penStyle()), "solid")
    custom = None
    if sl.useCustomDashPattern():
        pen = "custom"
        unit = sl.customDashPatternUnit()
        custom = [to_px(v, unit, context) for v in sl.customDashVector()]
    props = {
        "@line-color": _color(color),
        "@line-width": styles.line_width(width_px),
        "@line-opacity": styles.opacity(_alpha(color), alpha),
        "@line-cap": _CAP_STYLES.get(enum_int(sl.penCapStyle()), "round"),
    }
    if pen == "none":
        props["@line-opacity"] = 0
    else:
        dashes = styles.dasharray(pen, custom, width_px)
        if dashes:
            props["@line-dasharray"] = dashes
    return props


def line_props(symbol, context, alpha):
    # The top line is the one that reads as "the" line; casings sit below it.
    sl = _last(symbol, QgsSimpleLineSymbolLayer)
    if sl is not None:
        return _line_layer_props(sl, context, alpha)
    # Marker lines, arrows and the like: their color, at their width in mm.
    width_px = symbol.width() * styles.PX_PER_MM
    return {
        "@line-color": _color(symbol.color()),
        "@line-width": styles.line_width(width_px),
        "@line-opacity": styles.opacity(_alpha(symbol.color()), alpha),
    }


def fill_props(symbol, context, alpha):
    props = {}
    fill = _first(symbol, QgsSimpleFillSymbolLayer)

    # Fill
    if fill is not None:
        color = _dd(fill, "FillColor", context, fill.color(), "color")
        visible = enum_int(fill.brushStyle()) != _NO_BRUSH
        props["@fill-color"] = _color(color)
        props["@fill-opacity"] = styles.opacity(
            _alpha(color) if visible else 0, alpha)
    else:
        # Gradient, pattern and other fills: their main color, see-through.
        color = symbol.color()
        props["@fill-color"] = _color(color)
        props["@fill-opacity"] = styles.opacity(_alpha(color), alpha, 0.5)

    # Outline: a separate simple line layer wins over the fill's own stroke.
    outline = _last(symbol, QgsSimpleLineSymbolLayer)
    if outline is not None:
        props.update(_line_layer_props(outline, context, alpha))
    elif fill is not None and enum_int(fill.strokeStyle()) != 0:
        stroke = _dd(fill, "StrokeColor", context, fill.strokeColor(), "color")
        width = _dd(fill, "StrokeWidth", context, fill.strokeWidth(), "double")
        width_px = to_px(width, fill.strokeWidthUnit(), context,
                         fill.strokeWidthMapUnitScale())
        pen = _PEN_STYLES.get(enum_int(fill.strokeStyle()), "solid")
        props["@line-color"] = _color(stroke)
        props["@line-width"] = styles.line_width(width_px)
        props["@line-opacity"] = styles.opacity(_alpha(stroke), alpha)
        dashes = styles.dasharray(pen, None, width_px)
        if dashes:
            props["@line-dasharray"] = dashes
    else:
        props["@line-color"] = props["@fill-color"]
        props["@line-width"] = styles.LINE_WIDTH[0]
        props["@line-opacity"] = 0
    return props
