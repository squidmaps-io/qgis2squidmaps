# qgis2squidmaps

A QGIS plugin that publishes your project as a [squidmaps](https://squidmaps.io)
map. Pick layers, click **Create map**, and get a link you can share. You don't
host anything, and no HTML is generated.

It does the same job as [qgis2web](https://github.com/qgis2web/qgis2web), but
the output is different. qgis2web writes a Leaflet or OpenLayers website for
you to host. This plugin writes one
[squidmaps map document](https://squidmaps.io/docs/spec) and sends it to the
[ephemeral maps API](https://squidmaps.io/docs/api/ephemeral-maps).

## Installing

The plugin is in the official QGIS plugin repository:
[plugins.qgis.org/plugins/qgis2squidmaps](https://plugins.qgis.org/plugins/qgis2squidmaps/).
In QGIS, open **Plugins ▸ Manage and Install Plugins**, search for
**qgis2squidmaps** and click **Install Plugin**.

## Using it

**Web ▸ qgis2squidmaps ▸ Create squidmaps map** opens a dialog with two tabs.

**Layers**: every vector layer, top first. Visible layers start checked. For
each layer you can set:

| Column       | What it sets in squidmaps |
| ------------ | ------------------------- |
| Name         | An expression for each feature's `name`, shown as its popup title, tooltip and label. Defaults to the layer's label expression, or its display name. |
| Popup        | `@popup`: `card`, `panel` or `none`. |
| Popup fields | The fields listed in each feature's `description`, by their aliases, formatted as the attribute form shows them (value maps, dates and so on). Fields hidden in the form start unchecked. |
| Tooltip      | `@tooltip`. |
| Labels       | `@show-label`, with the layer's label color and size. Points only. |

**Map**: title and description (from the project's metadata), basemap (one
of squidmaps' light, streets, gray or dark, with or without their labels;
none; or an XYZ tile layer from the project; squidmaps light by default,
and your last choice is saved in the project), where
the map opens (fit to features, or the current map view, optionally with
panning locked to it), whether to export only features in view, and whether
to show the legend, feature list and search.

**Create map** sends the map and opens it in your browser. The link lasts an
hour after the last change; open it to add the map to your squidmaps account
and keep it. The map's id and edit token are saved in the project. After
that the button says **Update map**, which replaces the map's contents and
keeps the same link. Updates are accepted for 24 hours after the map is
created. If the map has expired, or has been added to an account, a new map
is created instead.

**Save JSON…** writes the map document to a file instead.

## How QGIS maps onto squidmaps

squidmaps keeps every feature's style in its own properties. So the plugin
doesn't translate renderers. It asks each layer's renderer which symbol it
draws a feature with (`symbolsForFeature`) and copies that symbol's look.
Single symbol, categorized, graduated, rule-based and other renderers all
work the same way, including rule scale ranges (at the canvas scale) and
data-defined fill, stroke, size and width.

| QGIS | squidmaps |
| ---- | --------- |
| Layer | `@folder` (the feature list lets visitors toggle it), plus legend rows |
| Layer order | `features` order, top first |
| Marker symbol (any shape, SVG, font) | `@point-type: circle` with its fill, stroke and size (diameter → radius) |
| Simple line (top one, if several) | `@line-color/width/opacity/dasharray/cap` |
| Simple fill + outline | `@fill-color/opacity` + `@line-*` |
| Gradient / pattern fills | Their main color at half opacity |
| Color alpha × symbol opacity × layer opacity | `@line-opacity`, `@fill-opacity` |
| Sizes in mm, pt, px, map units | CSS pixels at 96 dpi; map units at the canvas scale |
| XYZ tile layer | `basemap: {type: "XYZ"}`, if you pick it instead of a squidmaps basemap |
| Canvas extent | `extent.initialBounds` and `view` (and optionally `extent.bounds`) |
| Project title / abstract | `name` / `description` |

Geometries are reprojected to WGS84, curves are segmentized, Z and M are
dropped, and coordinates are rounded to 6 decimals. Features each get an id
like `layer-name-<fid>`.

### Not supported (yet)

- Raster layers, other than XYZ tiles used as the basemap.
- Marker shapes and SVG icons. Points become circles. squidmaps has Font
  Awesome icons, emoji and marker pins, which could be mapped to later.
- Labels on lines and polygons. These could become `@feature-type: "text"`
  features at their label positions.
- Heatmaps, clustering, 2.5D, and per-layer zoom visibility.
- Features with images (the API doesn't accept them).

### Limits

The API takes up to 5 MB per map; the plugin checks before sending. Adding a
map to an account is limited to 1,000 features and 1 MB of features, and the
plugin warns about that too. If you hit either limit, export fewer layers,
export only what's in view, or simplify geometries first.

## Development

```sh
make test      # unit tests for the QGIS-free modules (pip install jsonschema to validate against the spec)
make install   # symlink into your QGIS profile
make zip       # dist/qgis2squidmaps-<version>.zip, for Plugins ▸ Install from ZIP
make test-project  # rebuild test-project/test.qgz, a small sample project to try the plugin on (macOS QGIS.app)
```

| Module | |
| ------ | - |
| `styles.py`   | Pure helpers: colors, units, dashes, popup Markdown. |
| `document.py` | Pure: assembles and checks the map document. |
| `api.py`      | Ephemeral maps API client (QGIS network stack, urllib fallback). |
| `symbols.py`  | QGIS symbols → `@` properties. |
| `exporter.py` | Layers → features, legend, basemap, extent. |
| `dialog.py`, `plugin.py` | The UI. |

`tests/fixtures/map.schema.json` is a copy of
https://squidmaps.io/docs/map.schema.json; refresh it when the spec changes.

Supports QGIS 3.22+ and QGIS 4 (Qt6).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
