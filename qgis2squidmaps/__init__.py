# -*- coding: utf-8 -*-
"""qgis2squidmaps: publish a QGIS project as a squidmaps map."""


def classFactory(iface):
    from .plugin import Qgis2Squidmaps
    return Qgis2Squidmaps(iface)
