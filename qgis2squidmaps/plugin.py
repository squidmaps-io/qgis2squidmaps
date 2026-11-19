# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

MENU = "&qgis2squidmaps"


class Qgis2Squidmaps(object):

    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.action = None

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.svg"))
        self.action = QAction(icon, "Create squidmaps map",
                              self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu(MENU, self.action)
        self.iface.addWebToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginWebMenu(MENU, self.action)
        self.iface.removeWebToolBarIcon(self.action)
        if self.dialog is not None:
            self.dialog.close()

    def run(self):
        # A fresh dialog each time, so it reflects the project's current
        # layers and styles.
        from .dialog import MainDialog
        if self.dialog is not None:
            self.dialog.close()
        self.dialog = MainDialog(self.iface)
        self.dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.dialog.destroyed.connect(lambda: setattr(self, "dialog", None))
        self.dialog.show()
        self.dialog.raise_()
