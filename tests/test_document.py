import json
import os
import unittest

from qgis2squidmaps import document

SCHEMA = os.path.join(os.path.dirname(__file__), "fixtures", "map.schema.json")

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


def sample():
    point_style = {"@point-type": "circle", "@fill": "#D9664E",
                   "@radius": 6, "@stroke": "#FFFFFF", "@stroke-width": 1}
    area_style = {"@line-color": "#2F8A4E", "@line-width": 1,
                  "@line-opacity": 1, "@line-cap": "round",
                  "@line-dasharray": [4, 2],
                  "@fill-color": "#2F8A4E", "@fill-opacity": 0.4}
    features = [
        {"type": "Feature", "id": "cafes-1",
         "geometry": {"type": "Point", "coordinates": [-73.986645, 40.726721]},
         "properties": dict(point_style, name="Abraço", **{
             "@folder": "Cafés", "@popup": "card", "@tooltip": True,
             "description": "**Hours**: 8-4"})},
        {"type": "Feature", "id": "parks-1",
         "geometry": {"type": "Polygon", "coordinates": [[
             [-73.982288, 40.727809], [-73.979992, 40.726849],
             [-73.981247, 40.725085], [-73.982288, 40.727809]]]},
         "properties": dict(area_style, name="Tompkins", **{
             "@folder": "Parks", "@popup": "panel", "@tooltip": False})},
    ]
    rows = [
        {"label": "Cafés", "symbol": document.legend_symbol("point",
                                                            point_style)},
        {"label": "Parks", "symbol": document.legend_symbol("polygon",
                                                            area_style)},
        {"label": "Roads", "symbol": document.legend_symbol("line", {})},
    ]
    return document.build_document(
        features, name="Test map", description="From **QGIS**",
        basemap=document.squidmaps_basemap("gray"), legend_rows=rows,
        initial_bounds=[-74, 40.715, -73.97, 40.74],
        restrict_bounds=[-74.02, 40.7, -73.95, 40.75])


class DocumentTest(unittest.TestCase):

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_matches_schema(self):
        with open(SCHEMA) as f:
            schema = json.load(f)
        jsonschema.validate(sample(), schema)
        xyz = sample()
        xyz["basemap"] = document.xyz_basemap(
            "OSM", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", 0.8)
        jsonschema.validate(xyz, schema)
        jsonschema.validate(document.build_document([], name=""), schema)

    def test_view_follows_initial_bounds(self):
        doc = sample()
        self.assertEqual(doc["view"]["center"], [-73.985, 40.7275])

    def test_fit_to_features(self):
        doc = document.build_document([], name="x")
        self.assertIsNone(doc["view"])
        self.assertIsNone(doc["extent"]["initialBounds"])

    def test_bad_bounds_are_dropped(self):
        self.assertIsNone(document.clean_bounds([1, 1, 1, 1]))
        self.assertEqual(document.clean_bounds([-200, -90, 200, 90]),
                         [-180, -85.051129, 180, 85.051129])

    def test_legend_capped(self):
        rows = [{"label": str(i), "symbol": document.legend_symbol("line", {})}
                for i in range(60)]
        doc = document.build_document([], name="x", legend_rows=rows)
        self.assertEqual(len(doc["legend"]["rows"]), 50)

    def test_size_warnings(self):
        self.assertEqual(document.size_warnings(sample()), [])
        big = sample()
        big["features"] = big["features"] * 600
        self.assertEqual(len(document.size_warnings(big)), 1)


if __name__ == "__main__":
    unittest.main()
