"""Builds test-project/test.qgz: a small NYC project for trying the plugin.

Run with QGIS's Python (see Makefile target `test-project`).
"""
import os
from qgis.core import (
    QgsApplication, QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField, QgsFields, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol,
    QgsGraduatedSymbolRenderer, QgsRendererRange, QgsRuleBasedRenderer,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
    QgsEditorWidgetSetup, QgsReferencedRectangle, QgsRectangle,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

HERE = os.path.dirname(os.path.abspath(__file__))
GPKG = os.path.join(HERE, "test_data.gpkg")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

app = QgsApplication([], False)
app.initQgis()

if os.path.exists(GPKG):
    os.remove(GPKG)


def write(name, geom_type, fields, rows):
    qf = QgsFields()
    for fname, ftype in fields:
        qf.append(QgsField(fname, ftype))
    mem = QgsVectorLayer(f"{geom_type}?crs=EPSG:4326", name, "memory")
    mem.dataProvider().addAttributes(qf)
    mem.updateFields()
    feats = []
    for wkt, attrs in rows:
        f = QgsFeature(mem.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes(attrs)
        feats.append(f)
    mem.dataProvider().addFeatures(feats)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    opts.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteLayer
                                 if os.path.exists(GPKG)
                                 else QgsVectorFileWriter.CreateOrOverwriteFile)
    err = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem, GPKG, QgsCoordinateTransformContext(), opts)
    assert err[0] == QgsVectorFileWriter.NoError, err
    lyr = QgsVectorLayer(f"{GPKG}|layername={name}", name, "ogr")
    assert lyr.isValid(), name
    return lyr


# --- Points: categorized by type, labeled, value-map field -----------------
places = write("places", "Point",
    [("name", QVariant.String), ("type", QVariant.String),
     ("rating", QVariant.Int), ("opened", QVariant.Date),
     ("website", QVariant.String)],
    [("POINT(-73.9857 40.7484)", ["Empire State Building", "landmark", 5, "1931-05-01", "https://www.esbnyc.com"]),
     ("POINT(-73.9787 40.7614)", ["MoMA", "museum", 5, "1929-11-07", "https://www.moma.org"]),
     ("POINT(-73.9632 40.7794)", ["The Met", "museum", 4, "1870-04-13", "https://www.metmuseum.org"]),
     ("POINT(-73.9855 40.7580)", ["Times Square", "landmark", 3, None, None]),
     ("POINT(-73.9654 40.7829)", ["Central Park Zoo", "park", 4, "1864-01-01", None]),
     ("POINT(-74.0445 40.6892)", ["Statue of Liberty", "landmark", 5, "1886-10-28", "https://www.nps.gov/stli"]),
     ("POINT(-73.9969 40.7061)", ["Brooklyn Bridge Park", "park", 4, "2010-03-22", None]),
     ("POINT(-74.0134 40.7115)", ["9/11 Memorial", "museum", 5, "2011-09-11", "https://www.911memorial.org"])])

colors = {"landmark": "#e4572e", "museum": "#4c6ef5", "park": "#2f9e44"}
cats = []
for value, color in colors.items():
    s = QgsSymbol.defaultSymbol(places.geometryType())
    s.setColor(QColor(color))
    s.setSize(4)
    s.symbolLayer(0).setStrokeColor(QColor("white"))
    cats.append(QgsRendererCategory(value, s, value.title()))
places.setRenderer(QgsCategorizedSymbolRenderer("type", cats))

idx = places.fields().indexOf("type")
places.setEditorWidgetSetup(idx, QgsEditorWidgetSetup(
    "ValueMap", {"map": [{"Landmark": "landmark"}, {"Museum": "museum"}, {"Park": "park"}]}))
places.setFieldAlias(places.fields().indexOf("opened"), "Opened")
places.setFieldAlias(places.fields().indexOf("rating"), "Rating (1–5)")

pal = QgsPalLayerSettings()
pal.fieldName = "name"
fmt = QgsTextFormat()
fmt.setColor(QColor("#333333"))
fmt.setSize(9)
pal.setFormat(fmt)
places.setLabeling(QgsVectorLayerSimpleLabeling(pal))
places.setLabelsEnabled(True)

# --- Lines: graduated by daily riders, dashed ferry ------------------------
routes = write("routes", "LineString",
    [("route", QVariant.String), ("mode", QVariant.String), ("riders", QVariant.Int)],
    [("LINESTRING(-74.0134 40.7015, -74.0720 40.6437)", ["Staten Island Ferry", "ferry", 70000]),
     ("LINESTRING(-73.9969 40.7061, -73.9903 40.7140, -73.9857 40.7484, -73.9787 40.7614)", ["Downtown–Midtown", "subway", 250000]),
     ("LINESTRING(-73.9855 40.7580, -73.9632 40.7794, -73.9500 40.8000)", ["Upper East Side", "subway", 180000]),
     ("LINESTRING(-74.0134 40.7115, -74.0080 40.7300, -73.9969 40.7400, -73.9857 40.7484)", ["West Side", "bus", 30000])])

ranges = []
for lo, hi, w, c, lbl in [(0, 50000, 1.0, "#9ecae1", "< 50k"),
                           (50000, 200000, 2.0, "#4292c6", "50k – 200k"),
                           (200000, 1e9, 3.5, "#08519c", "> 200k")]:
    s = QgsSymbol.defaultSymbol(routes.geometryType())
    s.setColor(QColor(c))
    s.setWidth(w)
    ranges.append(QgsRendererRange(lo, hi, s, lbl))
routes.setRenderer(QgsGraduatedSymbolRenderer("riders", ranges))

# --- Polygons: rule-based, semi-transparent fills -------------------------
areas = write("areas", "Polygon",
    [("name", QVariant.String), ("kind", QVariant.String), ("acres", QVariant.Double)],
    [("POLYGON((-73.9819 40.7681, -73.9580 40.8006, -73.9498 40.7969, -73.9737 40.7644, -73.9819 40.7681))", ["Central Park", "park", 843.0]),
     ("POLYGON((-73.9764 40.6602, -73.9620 40.6720, -73.9590 40.6620, -73.9700 40.6520, -73.9764 40.6602))", ["Prospect Park", "park", 526.0]),
     ("POLYGON((-74.0190 40.7000, -74.0000 40.7000, -73.9980 40.7150, -74.0160 40.7180, -74.0190 40.7000))", ["Financial District", "district", 300.0])])

root = QgsRuleBasedRenderer.Rule(None)
for label, expr, fill, stroke in [("Parks", "\"kind\" = 'park'", "#69db7c", "#2b8a3e"),
                                  ("Other areas", "ELSE", "#ffd43b", "#e67700")]:
    s = QgsSymbol.defaultSymbol(areas.geometryType())
    s.setColor(QColor(fill))
    s.setOpacity(0.5)
    s.symbolLayer(0).setStrokeColor(QColor(stroke))
    s.symbolLayer(0).setStrokeWidth(0.6)
    root.appendChild(QgsRuleBasedRenderer.Rule(s, 0, 0, expr if expr != "ELSE" else "ELSE", label))
areas.setRenderer(QgsRuleBasedRenderer(root))

# --- Hidden layer (should start unchecked in the dialog) ------------------
hidden = write("hidden_layer", "Point", [("note", QVariant.String)],
               [("POINT(-73.95 40.73)", ["You should not see me by default"])])

# --- Basemap --------------------------------------------------------------
osm = QgsRasterLayer(
    "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
    "OpenStreetMap", "wms")
assert osm.isValid()

# --- Project --------------------------------------------------------------
proj = QgsProject.instance()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
md = proj.metadata()
md.setTitle("qgis2squidmaps test map")
md.setAbstract("A few New York places, routes and areas for testing the plugin.")
proj.setMetadata(md)
proj.setTitle("qgis2squidmaps test map")
for lyr in (osm, areas, routes, places, hidden):  # added bottom-up
    proj.addMapLayer(lyr)
# addMapLayer inserts at top; set explicit order: places, routes, areas, hidden, osm
tree = proj.layerTreeRoot()
order = [places, routes, areas, hidden, osm]
tree.setHasCustomLayerOrder(False)
for i, lyr in enumerate(order):
    node = tree.findLayer(lyr.id())
    clone = node.clone()
    tree.insertChildNode(i, clone)
    node.parent().removeChildNode(node)
tree.findLayer(hidden.id()).setItemVisibilityChecked(False)

# Open on lower Manhattan / Brooklyn
proj.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(
    QgsRectangle(-74.08, 40.63, -73.93, 40.81), WGS84))

out = os.path.join(HERE, "test.qgz")
assert proj.write(out), "failed to write project"
print("wrote", out)
app.exitQgis()
