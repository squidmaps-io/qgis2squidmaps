PLUGIN = qgis2squidmaps
VERSION = $(shell sed -n 's/^version=//p' $(PLUGIN)/metadata.txt)
QGIS_PLUGINS ?= $(HOME)/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins

.PHONY: test zip install clean test-project

test:
	python3 -m unittest discover -s tests -t . -v

zip: clean
	mkdir -p dist
	cp LICENSE README.md $(PLUGIN)/
	zip -r dist/$(PLUGIN)-$(VERSION).zip $(PLUGIN) -x '*__pycache__*' '*.pyc' '*.DS_Store'
	rm $(PLUGIN)/LICENSE $(PLUGIN)/README.md

# Symlink the plugin into your QGIS profile for development (macOS path by
# default; override QGIS_PLUGINS on Linux/Windows). Restart QGIS, or use the
# Plugin Reloader plugin, after changes.
install:
	mkdir -p "$(QGIS_PLUGINS)"
	ln -sfn "$(CURDIR)/$(PLUGIN)" "$(QGIS_PLUGINS)/$(PLUGIN)"

# Rebuild test-project/test.qgz (sample layers) with QGIS's bundled Python.
QGIS_APP ?= /Applications/QGIS.app/Contents
test-project:
	cd test-project && PYTHONHOME="$(QGIS_APP)/Frameworks" PYTHONPATH="$(QGIS_APP)/Resources/python" \
	  PROJ_DATA="$(QGIS_APP)/Resources/qgis/proj" GDAL_DATA="$(QGIS_APP)/Resources/qgis/gdal" \
	  QT_QPA_PLATFORM=offscreen "$(QGIS_APP)/MacOS/python3.12" make_project.py

clean:
	rm -rf dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
