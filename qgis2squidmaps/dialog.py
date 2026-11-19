# -*- coding: utf-8 -*-
"""The plugin's dialog: choose layers and map settings, then publish."""

import datetime
import os

from qgis.core import Qgis, QgsProject
from qgis.gui import QgsFieldExpressionWidget
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QGuiApplication
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import api, document, exporter

SCOPE = "qgis2squidmaps"
_SUCCESS = getattr(Qgis, "Success", None) or Qgis.MessageLevel.Success
UPDATE_WINDOW = datetime.timedelta(hours=24)  # PUTs accepted after creation

# Qt enums, scoped so they work with PyQt5 and PyQt6.
CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked
USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable
ITEM_ENABLED = Qt.ItemFlag.ItemIsEnabled
USER_ROLE = Qt.ItemDataRole.UserRole

COL_LAYER, COL_NAME, COL_POPUP, COL_FIELDS, COL_TOOLTIP, COL_LABELS = range(6)

BASEMAP_CHOICES = [
    ("squidmaps light", ("squidmaps", "light")),
    ("squidmaps streets", ("squidmaps", "streets")),
    ("squidmaps gray", ("squidmaps", "gray")),
    ("squidmaps dark", ("squidmaps", "dark")),
    ("None", ("none", None)),
]


class FieldsDialog(QDialog):
    """Pick the fields shown in a layer's popups."""

    def __init__(self, layer, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Popup fields: {}".format(layer.name()))
        self.list = QListWidget()
        for i, field in enumerate(layer.fields()):
            alias = layer.attributeDisplayName(i)
            text = field.name() if alias == field.name() else \
                "{} ({})".format(alias, field.name())
            item = QListWidgetItem(text)
            item.setData(USER_ROLE, field.name())
            item.setFlags(item.flags() | USER_CHECKABLE)
            item.setCheckState(CHECKED if field.name() in selected
                               else UNCHECKED)
            self.list.addItem(item)
        all_button = QPushButton("All")
        none_button = QPushButton("None")
        all_button.clicked.connect(lambda: self._set_all(CHECKED))
        none_button.clicked.connect(lambda: self._set_all(UNCHECKED))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def _set_all(self, state):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def selected(self):
        return [self.list.item(i).data(USER_ROLE)
                for i in range(self.list.count())
                if self.list.item(i).checkState() == CHECKED]


class MainDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.project = QgsProject.instance()
        self.popup_fields = {}  # layer id -> [field names]
        self.setWindowTitle("Create squidmaps map")
        self.resize(900, 600)

        tabs = QTabWidget()
        tabs.addTab(self._layers_tab(), "Layers")
        tabs.addTab(self._map_tab(), "Map")

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setOpenExternalLinks(True)
        self.status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)

        self.update_existing = QCheckBox(
            "Update the map I published before (the link stays the same)")
        self.update_existing.toggled.connect(self._refresh_publish_label)

        self.save_button = QPushButton("Save JSON…")
        self.copy_button = QPushButton("Copy link")
        self.publish_button = QPushButton("Create map")
        self.publish_button.setDefault(True)
        close_button = QPushButton("Close")
        self.save_button.clicked.connect(self.save_json)
        self.copy_button.clicked.connect(self.copy_link)
        self.publish_button.clicked.connect(self.publish)
        close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addStretch()
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.publish_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self.update_existing)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        self._show_saved_map()

    # --- layout -------------------------------------------------------------

    def _layers_tab(self):
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            ["Layer", "Name (title, tooltip, label)", "Popup",
             "Popup fields", "Tooltip", "Labels"])
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setSectionResizeMode(COL_LAYER,
                                    QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)

        for layer, visible in exporter.exportable_layers(self.project):
            item = QTreeWidgetItem(self.tree)
            item.setText(COL_LAYER, layer.name())
            item.setData(COL_LAYER, USER_ROLE, layer.id())
            item.setFlags(item.flags() | USER_CHECKABLE)
            item.setCheckState(COL_LAYER, CHECKED if visible else UNCHECKED)

            name = QgsFieldExpressionWidget()
            name.setLayer(layer)
            name.setExpression(exporter.default_name_expression(layer))
            self.tree.setItemWidget(item, COL_NAME, name)

            popup = QComboBox()
            popup.addItems(["card", "panel", "none"])
            self.tree.setItemWidget(item, COL_POPUP, popup)

            self.popup_fields[layer.id()] = \
                exporter.default_popup_fields(layer)
            fields_button = QPushButton()
            fields_button.clicked.connect(
                lambda _=False, l=layer, b=fields_button:
                self._choose_fields(l, b))
            self._label_fields_button(layer, fields_button)
            self.tree.setItemWidget(item, COL_FIELDS, fields_button)

            item.setCheckState(COL_TOOLTIP, CHECKED)
            labels_ok = exporter.geometry_kind(layer) == "point"
            item.setCheckState(COL_LABELS, CHECKED
                               if labels_ok and layer.labelsEnabled()
                               else UNCHECKED)
            if not labels_ok:
                item.setToolTip(COL_LABELS,
                                "squidmaps draws labels on points only.")

        note = QLabel(
            "Layers are listed in the order they're drawn, top first. Each "
            "becomes a folder in the map. Every feature is styled with the "
            "symbol QGIS draws it with: points become circles, lines a "
            "single stroke, polygons a fill and outline.")
        note.setWordWrap(True)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(self.tree)
        layout.addWidget(note)
        return widget

    def _map_tab(self):
        metadata = self.project.metadata()
        title = self.project.title() or metadata.title() or \
            os.path.splitext(self.project.baseName() or "")[0] or "QGIS map"
        self.title = QLineEdit(title)
        self.title.setMaxLength(100)
        self.description = QPlainTextEdit(metadata.abstract() or "")
        self.description.setPlaceholderText("Markdown, shown under the title.")

        # squidmaps' own basemaps come first and are the default; the
        # project's XYZ tile layers are offered after them.
        self.basemap = QComboBox()
        for label, value in BASEMAP_CHOICES:
            self.basemap.addItem(label, value)
        xyz = exporter.xyz_layers(self.project)
        if xyz:
            self.basemap.insertSeparator(self.basemap.count())
        for layer, _visible in xyz:
            self.basemap.addItem("Tiles from project: {}".format(layer.name()),
                                 ("xyz", layer.id()))
        saved = self.project.readEntry(SCOPE, "basemap", "")[0]
        if saved:
            kind, _, value = saved.partition(":")
            for index in range(self.basemap.count()):
                if self.basemap.itemData(index) == (kind, value or None):
                    self.basemap.setCurrentIndex(index)
                    break
        self.basemap_labels = QCheckBox("Show the basemap's labels")
        self.basemap_labels.setChecked(
            self.project.readBoolEntry(SCOPE, "basemapLabels", True)[0])
        self.basemap.currentIndexChanged.connect(self._basemap_changed)
        self._basemap_changed()

        self.extent = QComboBox()
        self.extent.addItem("Fit to the features", "fit")
        self.extent.addItem("The current map view", "canvas")
        self.extent.setCurrentIndex(1)
        self.only_in_extent = QCheckBox(
            "Only export features in the current map view")
        self.restrict = QCheckBox("Don't let visitors pan away from it")
        self.extent.currentIndexChanged.connect(
            lambda: self.restrict.setEnabled(
                self.extent.currentData() == "canvas"))

        self.legend = QCheckBox("Legend")
        self.legend.setChecked(True)
        self.feature_list = QCheckBox("Feature list, by layer")
        self.feature_list.setChecked(True)
        self.search = QCheckBox("Search box")
        self.include_attributes = QCheckBox(
            "Keep every attribute in the features' data (not only popup "
            "fields)")
        self.include_attributes.setChecked(True)

        widget = QWidget()
        form = QFormLayout(widget)
        form.addRow("Title", self.title)
        form.addRow("Description", self.description)
        form.addRow("Basemap", self.basemap)
        form.addRow("", self.basemap_labels)
        form.addRow("Open the map on", self.extent)
        form.addRow("", self.restrict)
        form.addRow("", self.only_in_extent)
        form.addRow("Show", self.legend)
        form.addRow("", self.feature_list)
        form.addRow("", self.search)
        form.addRow("Data", self.include_attributes)
        return widget

    def _choose_fields(self, layer, button):
        dialog = FieldsDialog(layer, self.popup_fields[layer.id()], self)
        if dialog.exec():
            self.popup_fields[layer.id()] = dialog.selected()
            self._label_fields_button(layer, button)

    def _label_fields_button(self, layer, button):
        chosen = len(self.popup_fields[layer.id()])
        total = layer.fields().count()
        button.setText("All ({})".format(total) if chosen == total
                       else "{} of {}".format(chosen, total))

    # --- collecting options -------------------------------------------------

    def layer_options(self):
        options = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(COL_LAYER) != CHECKED:
                continue
            layer = self.project.mapLayer(item.data(COL_LAYER, USER_ROLE))
            if layer is None:
                continue
            options.append(exporter.LayerOptions(
                layer,
                name_expression=self.tree.itemWidget(item, COL_NAME)
                .expression(),
                popup_fields=self.popup_fields.get(layer.id(), []),
                popup=self.tree.itemWidget(item, COL_POPUP).currentText(),
                tooltip=item.checkState(COL_TOOLTIP) == CHECKED,
                show_labels=item.checkState(COL_LABELS) == CHECKED,
            ))
        return options

    def _basemap_changed(self):
        # Only squidmaps' basemaps have labels that can be turned off.
        kind = (self.basemap.currentData() or (None, None))[0]
        self.basemap_labels.setEnabled(kind == "squidmaps")

    def export_options(self):
        canvas = self.iface.mapCanvas()
        kind, value = self.basemap.currentData()
        # Remember the choice in the project for next time.
        self.project.writeEntry(SCOPE, "basemap",
                                "{}:{}".format(kind, value or ""))
        self.project.writeEntryBool(SCOPE, "basemapLabels",
                                    self.basemap_labels.isChecked())
        if kind == "squidmaps":
            basemap = document.squidmaps_basemap(
                value, labels=self.basemap_labels.isChecked())
        elif kind == "xyz":
            layer = self.project.mapLayer(value)
            basemap = exporter.xyz_basemap_for(layer) if layer else None
        else:
            basemap = None

        canvas_extent = (canvas.extent(),
                         canvas.mapSettings().destinationCrs())
        use_canvas = self.extent.currentData() == "canvas"
        return exporter.ExportOptions(
            title=self.title.text().strip(),
            description=self.description.toPlainText().strip(),
            basemap=basemap,
            legend=self.legend.isChecked(),
            feature_list=self.feature_list.isChecked(),
            search=self.search.isChecked(),
            open_extent=canvas_extent if use_canvas else None,
            filter_extent=canvas_extent if self.only_in_extent.isChecked()
            else None,
            restrict_to_extent=use_canvas and self.restrict.isChecked(),
            include_attributes=self.include_attributes.isChecked(),
            render_context=exporter.make_render_context(canvas),
        )

    def build(self):
        layers = self.layer_options()
        if not layers:
            self._set_status("Check at least one layer to export.", error=True)
            return None
        export = self.export_options()
        self._set_status("Exporting…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return exporter.export_document(layers, export, self.project)
        finally:
            QApplication.restoreOverrideCursor()

    # --- actions ------------------------------------------------------------

    def save_json(self):
        built = self.build()
        if not built:
            return
        doc, warnings = built
        path, _ = QFileDialog.getSaveFileName(
            self, "Save squidmaps map", "{}.json".format(
                doc["name"]), "squidmaps map (*.json)")
        if not path:
            self._set_status("")
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(document.to_json(doc, indent=2))
        self._set_status("Saved {} features to {}.{}".format(
            len(doc["features"]), path, self._warnings_html(warnings)))

    def publish(self):
        built = self.build()
        if not built:
            return
        doc, warnings = built
        if any("5 MB" in w for w in warnings):
            self._set_status(self._warnings_html(warnings), error=True)
            return

        saved = self._saved_map()
        updating = self.update_existing.isChecked() and saved is not None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if updating:
                try:
                    result = api.update_map(saved["id"], saved["token"], doc)
                    result.setdefault("url", saved["url"])
                    result["editToken"] = saved["token"]
                    result["createdAt"] = saved["created"]
                except api.SquidmapsError as e:
                    if e.status not in (403, 404, 409):
                        raise
                    reason = {
                        403: "its edit token no longer matches",
                        404: "it has expired",
                        409: "it's been added to a squidmaps account, so "
                             "it can only be changed in squidmaps",
                    }[e.status]
                    warnings.insert(0, "Couldn't update the earlier map "
                                       "because {}, so this is a new one."
                                    .format(reason))
                    updating = False
            if not updating:
                result = api.create_map(doc)
                result["createdAt"] = _now()
        except api.SquidmapsError as e:
            self._set_status(str(e), error=True)
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._save_map(result)
        url = result["url"]
        verb = "Updated" if updating else "Created"
        expires = _local_time(result.get("expiresAt"))
        self._set_status(
            '{} <a href="{url}">{url}</a> with {n} features. The link works '
            'until {expires}, an hour after the last change; open it to add '
            'the map to your squidmaps account and keep it.{w}'.format(
                verb, url=url, n=len(doc["features"]), expires=expires,
                w=self._warnings_html(warnings)))
        self.iface.messageBar().pushMessage(
            "squidmaps", "{} {}".format(verb, url), _SUCCESS, 10)
        QDesktopServices.openUrl(QUrl(url))

    def copy_link(self):
        saved = self._saved_map()
        if saved:
            QGuiApplication.clipboard().setText(saved["url"])
            self._set_status("Copied {}".format(saved["url"]))

    # --- the published map, kept in the project -----------------------------

    def _saved_map(self):
        read = self.project.readEntry
        map_id = read(SCOPE, "mapId", "")[0]
        token = read(SCOPE, "editToken", "")[0]
        url = read(SCOPE, "url", "")[0]
        created = read(SCOPE, "createdAt", "")[0]
        if not (map_id and token and url):
            return None
        return {"id": map_id, "token": token, "url": url, "created": created}

    def _save_map(self, result):
        write = self.project.writeEntry
        write(SCOPE, "mapId", result["id"])
        write(SCOPE, "editToken", result["editToken"])
        write(SCOPE, "url", result["url"])
        write(SCOPE, "createdAt", result.get("createdAt") or _now())
        self._show_saved_map()

    def _show_saved_map(self):
        saved = self._saved_map()
        updatable = saved is not None and _within_update_window(
            saved["created"])
        self.update_existing.setVisible(updatable)
        self.update_existing.setChecked(updatable)
        self.copy_button.setVisible(saved is not None)
        if saved is not None and not self.status.text():
            self._set_status('Last published: <a href="{0}">{0}</a>'.format(
                saved["url"]))
        self._refresh_publish_label()

    def _refresh_publish_label(self):
        updating = not self.update_existing.isHidden() and \
            self.update_existing.isChecked()
        self.publish_button.setText("Update map" if updating else "Create map")

    # --- status -------------------------------------------------------------

    def _set_status(self, html, error=False):
        self.status.setStyleSheet("color: #B3261E;" if error else "")
        self.status.setText(html)
        QApplication.processEvents()

    @staticmethod
    def _warnings_html(warnings):
        if not warnings:
            return ""
        return "<ul>{}</ul>".format(
            "".join("<li>{}</li>".format(w) for w in warnings))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _parse_time(text):
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _within_update_window(created):
    when = _parse_time(created)
    if when is None:
        return True  # let the API decide
    return datetime.datetime.now(datetime.timezone.utc) - when < UPDATE_WINDOW


def _local_time(text):
    when = _parse_time(text)
    if when is None:
        return "an hour from now"
    return when.astimezone().strftime("%H:%M")
