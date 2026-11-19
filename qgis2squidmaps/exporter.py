# -*- coding: utf-8 -*-
"""Turn QGIS layers into a squidmaps map document."""

import json
import math

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsRenderContext,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)

from . import document, styles
from .symbols import enum_int, geometry_kind, symbol_props

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
POPUP_TYPES = ("card", "panel", "none")


class LayerOptions(object):
    """How one vector layer is exported."""

    def __init__(self, layer, name_expression=None, popup_fields=None,
                 popup="card", tooltip=True, show_labels=None):
        self.layer = layer
        self.name_expression = (default_name_expression(layer)
                                if name_expression is None
                                else name_expression)
        self.popup_fields = (default_popup_fields(layer)
                             if popup_fields is None else list(popup_fields))
        self.popup = popup if popup in POPUP_TYPES else "card"
        self.tooltip = tooltip
        self.show_labels = (layer.labelsEnabled() if show_labels is None
                            else show_labels)


class ExportOptions(object):
    """Map-wide settings."""

    def __init__(self, title="", description="", basemap=None, legend=True,
                 feature_list=True, search=False, open_extent=None,
                 filter_extent=None, restrict_to_extent=False,
                 include_attributes=True, render_context=None):
        self.title = title
        self.description = description
        self.basemap = basemap
        self.legend = legend
        self.feature_list = feature_list
        self.search = search
        # Extents are (QgsRectangle, QgsCoordinateReferenceSystem) pairs.
        # open_extent: what the map opens on; None fits it to its features.
        # filter_extent: only export features inside it; None exports all.
        self.open_extent = open_extent
        self.filter_extent = filter_extent
        self.restrict_to_extent = restrict_to_extent
        self.include_attributes = include_attributes
        self.render_context = render_context


# --- defaults -----------------------------------------------------------------

def _label_settings(layer):
    if not layer.labelsEnabled():
        return None
    labeling = layer.labeling()
    if isinstance(labeling, QgsVectorLayerSimpleLabeling):
        return labeling.settings()
    return None


def default_name_expression(layer):
    """The label expression if the layer is labelled, else its display name."""
    settings = _label_settings(layer)
    if settings is not None and settings.fieldName:
        if settings.isExpression:
            return settings.fieldName
        return QgsExpression.quotedColumnRef(settings.fieldName)
    return layer.displayExpression()


def is_hidden_field(layer, index):
    return layer.editorWidgetSetup(index).type() == "Hidden"


def default_popup_fields(layer):
    """Every field not hidden in the attribute form, as qgis2web does."""
    return [f.name() for i, f in enumerate(layer.fields())
            if not is_hidden_field(layer, i)]


def exportable_layers(project=None):
    """Vector layers with geometry, in layer-tree order, top first."""
    project = project or QgsProject.instance()
    root = project.layerTreeRoot()
    layers = []
    for node in root.findLayers():
        layer = node.layer()
        if isinstance(layer, QgsVectorLayer) and layer.isSpatial() \
                and geometry_kind(layer) is not None:
            layers.append((layer, node.isVisible()))
    return layers


def xyz_layers(project=None):
    """Raster XYZ tile layers that can be the map's basemap, top first."""
    project = project or QgsProject.instance()
    found = []
    for node in project.layerTreeRoot().findLayers():
        layer = node.layer()
        if not isinstance(layer, QgsRasterLayer) or \
                layer.providerType() != "wms":
            continue
        uri = QgsProviderRegistry.instance().decodeUri("wms", layer.source())
        if uri.get("type") != "xyz" or not uri.get("url"):
            continue
        found.append((layer, node.isVisible()))
    return found


def xyz_basemap_for(layer):
    uri = QgsProviderRegistry.instance().decodeUri("wms", layer.source())
    url = uri.get("url", "")
    tms = "{-y}" in url
    url = url.replace("{-y}", "{y}")
    opacity = 1.0
    try:
        opacity = layer.renderer().opacity()
    except Exception:
        pass
    return document.xyz_basemap(layer.name(), url, opacity, tms)


def make_render_context(canvas=None):
    """A render context that converts symbol units to CSS pixels (96 dpi)."""
    if canvas is not None:
        context = QgsRenderContext.fromMapSettings(canvas.mapSettings())
    else:
        context = QgsRenderContext()
    context.setScaleFactor(styles.PX_PER_MM)
    return context


# --- values -------------------------------------------------------------------

def is_null(value):
    if value is None:
        return True
    is_null_fn = getattr(value, "isNull", None)
    try:
        return bool(is_null_fn()) if callable(is_null_fn) else False
    except Exception:
        return False


def json_value(value):
    """An attribute value as something json.dumps accepts."""
    if is_null(value):
        return None
    if isinstance(value, bool) or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return None
    if type(value).__name__ in ("QByteArray",):
        return None
    for method in ("toPyDateTime", "toPyDate", "toPyTime"):
        fn = getattr(value, method, None)
        if callable(fn):
            try:
                return fn().isoformat()
            except Exception:
                pass
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class _FieldFormatter(object):
    """Shows values as the attribute form does: value maps, dates and so on."""

    def __init__(self, layer):
        self.layer = layer
        registry = QgsApplication.fieldFormatterRegistry()
        self.formatters = []
        for i in range(layer.fields().count()):
            setup = layer.editorWidgetSetup(i)
            formatter = registry.fieldFormatter(setup.type())
            config = setup.config()
            try:
                cache = formatter.createCache(layer, i, config)
            except Exception:
                cache = None
            self.formatters.append((formatter, config, cache))

    def text(self, index, value):
        if is_null(value):
            return None
        formatter, config, cache = self.formatters[index]
        try:
            return formatter.representValue(self.layer, index, config, cache,
                                            value)
        except Exception:
            return str(value)


# --- geometry -----------------------------------------------------------------

def geojson_geometry(geometry, transform):
    """A GeoJSON geometry dict in WGS84, 2D, at most 6 decimals."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return None
    geom = QgsGeometry(geometry)
    if QgsWkbTypes.isCurvedType(geom.wkbType()):
        geom = QgsGeometry(geom.constGet().segmentize())
    abstract = geom.get()
    abstract.dropZValue()
    abstract.dropMValue()
    try:
        geom.transform(transform)
    except Exception:
        return None
    if geom.isEmpty():
        return None
    return json.loads(geom.asJson(6))


# --- layers -------------------------------------------------------------------

def _transform_extent_to(extent, layer_crs, project):
    rect, crs = extent
    if crs == layer_crs:
        return rect
    return QgsCoordinateTransform(crs, layer_crs, project) \
        .transformBoundingBox(rect)


def export_layer(options, export, project, used_ids, feedback=None):
    """(features, legend_rows) for one layer."""
    layer = options.layer
    kind = geometry_kind(layer)
    folder = styles.truncate(layer.name(), 100) or "Layer"
    prefix = styles.slug(layer.name())
    transform = QgsCoordinateTransform(layer.crs(), WGS84, project)
    layer_opacity = layer.opacity()

    context = QgsRenderContext(export.render_context) \
        if export.render_context is not None else make_render_context()
    context.setScaleFactor(styles.PX_PER_MM)
    exp_context = QgsExpressionContext(
        QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    context.setExpressionContext(exp_context)

    name_exp = None
    if options.name_expression:
        name_exp = QgsExpression(options.name_expression)
        name_exp.prepare(context.expressionContext())
        if name_exp.hasParserError():
            name_exp = None

    fields = layer.fields()
    popup_indexes = [fields.indexOf(n) for n in options.popup_fields
                     if fields.indexOf(n) >= 0]
    formatter = _FieldFormatter(layer)
    label_props = _label_props(layer) if (options.show_labels and
                                          kind == "point") else {}

    request = QgsFeatureRequest()
    if export.filter_extent is not None:
        request.setFilterRect(
            _transform_extent_to(export.filter_extent, layer.crs(), project))

    renderer = layer.renderer().clone() if layer.renderer() else None
    features = []
    if renderer is not None:
        renderer.startRender(context, fields)
    try:
        total = max(1, layer.featureCount())
        for n, feature in enumerate(layer.getFeatures(request)):
            if feedback is not None and feedback.isCanceled():
                break
            context.expressionContext().setFeature(feature)

            symbol = None
            if renderer is not None:
                symbols = renderer.symbolsForFeature(feature, context)
                if not symbols:
                    continue  # the layer's style doesn't draw it
                symbol = symbols[0]

            geometry = geojson_geometry(feature.geometry(), transform)
            if geometry is None:
                continue

            props = {}
            if export.include_attributes:
                for i, field in enumerate(fields):
                    key = field.name()
                    if key.startswith("@") or key in ("name", "description"):
                        continue
                    props[key] = json_value(feature.attribute(i))

            if name_exp is not None:
                value = name_exp.evaluate(context.expressionContext())
                if not is_null(value) and str(value).strip():
                    props["name"] = str(value)
            rows = [(layer.attributeDisplayName(i),
                     formatter.text(i, feature.attribute(i)))
                    for i in popup_indexes]
            description = styles.popup_markdown(rows)
            if description:
                props["description"] = description

            props["@folder"] = folder
            props["@popup"] = options.popup
            props["@tooltip"] = bool(options.tooltip and "name" in props)
            props.update(symbol_props(symbol, kind, context, layer_opacity))
            if label_props and "name" in props:
                props.update(label_props)

            fid = "{}-{}".format(prefix, feature.id())
            while fid in used_ids:
                fid += "-1"
            used_ids.add(fid)
            features.append({
                "type": "Feature",
                "id": fid,
                "geometry": geometry,
                "properties": props,
            })
            if feedback is not None and n % 200 == 0:
                feedback.setProgress(100.0 * n / total)
    finally:
        if renderer is not None:
            renderer.stopRender(context)

    # Legend symbols are drawn as styled, not for any one feature.
    context.expressionContext().setFeature(QgsFeature())
    legend_rows = _legend_rows(layer, renderer, kind, context, layer_opacity)
    return features, legend_rows


def _label_props(layer):
    settings = _label_settings(layer)
    props = {"@show-label": True}
    if settings is None:
        return props
    fmt = settings.format()
    color = fmt.color()
    props["@label-color"] = styles.hex_color(color.red(), color.green(),
                                             color.blue())
    props["@label-size"] = styles.label_size(fmt.size())
    return props


def _legend_rows(layer, renderer, kind, context, layer_opacity):
    if renderer is None:
        return []
    rows = []
    items = [i for i in renderer.legendSymbolItems() if i.symbol() is not None]
    for item in items:
        props = symbol_props(item.symbol(), kind, context, layer_opacity)
        label = layer.name() if len(items) == 1 else (item.label() or
                                                      layer.name())
        rows.append({
            "label": styles.truncate(label, 100),
            "symbol": document.legend_symbol(kind, props),
        })
    return rows


def export_document(layer_options, export, project=None, feedback=None):
    """The whole squidmaps map document, plus a list of warnings."""
    project = project or QgsProject.instance()
    features, legend_rows, warnings = [], [], []
    used_ids = set()
    for options in layer_options:
        f, rows = export_layer(options, export, project, used_ids, feedback)
        features.extend(f)
        legend_rows.extend(rows)
        if not f:
            warnings.append("{} has no features to export.".format(
                options.layer.name()))

    if len(legend_rows) > document.MAX_LEGEND_ROWS:
        warnings.append("The legend has {} rows; squidmaps shows the first "
                        "50.".format(len(legend_rows)))

    initial = restrict = None
    if export.open_extent is not None:
        rect, crs = export.open_extent
        wgs = QgsCoordinateTransform(crs, WGS84, project) \
            .transformBoundingBox(rect)
        bounds = [wgs.xMinimum(), wgs.yMinimum(), wgs.xMaximum(),
                  wgs.yMaximum()]
        initial = bounds
        if export.restrict_to_extent:
            restrict = bounds

    doc = document.build_document(
        features,
        name=export.title,
        description=export.description,
        basemap=export.basemap,
        legend_rows=legend_rows if export.legend else None,
        initial_bounds=initial,
        restrict_bounds=restrict,
        feature_list=export.feature_list,
        search=export.search,
    )
    warnings.extend(document.size_warnings(doc))
    return doc, warnings
