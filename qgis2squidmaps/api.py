# -*- coding: utf-8 -*-
"""Client for the squidmaps ephemeral maps API.

https://squidmaps.io/docs/api/ephemeral-maps

Inside QGIS, requests go through QGIS's network manager so its proxy and SSL
settings apply. Outside QGIS (tests, scripts) it falls back to urllib.
"""

import json

API_BASE = "https://squidmaps.io/api"
USER_AGENT = "qgis2squidmaps"


class SquidmapsError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message

    def __str__(self):
        if self.status:
            return "squidmaps returned {}: {}".format(self.status, self.message)
        return self.message


def create_map(document, base=API_BASE):
    """POST a new ephemeral map. Returns {id, url, editToken, expiresAt}."""
    return _request("POST", base + "/ephemeral-maps", document)


def update_map(map_id, edit_token, document, base=API_BASE):
    """PUT the whole document over an existing map. Returns {id, url, expiresAt}."""
    return _request("PUT", "{}/ephemeral-maps/{}".format(base, map_id),
                    document, token=edit_token)


def preview_url(map_id, width=1200, height=630, base=API_BASE):
    return "{}/ephemeral-maps/{}/preview.jpg?width={}&height={}".format(
        base, map_id, width, height)


def _request(method, url, document, token=None):
    body = json.dumps(document, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        status, raw = _send_qgis(method, url, body, headers)
    except ImportError:
        status, raw = _send_urllib(method, url, body, headers)
    return _parse(status, raw)


def _parse(status, raw):
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        data = {}
    if status is None or status >= 400:
        message = data.get("message") if isinstance(data, dict) else None
        if not message:
            message = raw.decode("utf-8", "replace")[:500] if raw else \
                "No response from squidmaps."
        raise SquidmapsError(status, message)
    return data


def _send_qgis(method, url, body, headers):
    from qgis.core import QgsBlockingNetworkRequest  # ImportError outside QGIS
    from qgis.PyQt.QtCore import QByteArray, QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    request = QNetworkRequest(QUrl(url))
    for key, value in headers.items():
        request.setRawHeader(key.encode("ascii"), value.encode("utf-8"))

    blocking = QgsBlockingNetworkRequest()
    payload = QByteArray(body)
    if method == "POST":
        blocking.post(request, payload, True)
    elif method == "PUT" and hasattr(blocking, "put"):
        blocking.put(request, payload)
    else:
        # Older QGIS without QgsBlockingNetworkRequest.put.
        raise ImportError("no blocking PUT")

    reply = blocking.reply()
    status = reply.attribute(_status_attribute(QNetworkRequest))
    raw = bytes(reply.content())
    if status is None and not raw:
        raise SquidmapsError(None, blocking.errorMessage() or
                             "Couldn't reach squidmaps.")
    return (int(status) if status is not None else None), raw


def _status_attribute(QNetworkRequest):
    attr = getattr(QNetworkRequest, "Attribute", None)
    if attr is not None and hasattr(attr, "HttpStatusCodeAttribute"):
        return attr.HttpStatusCodeAttribute
    return QNetworkRequest.HttpStatusCodeAttribute


def _send_urllib(method, url, body, headers):
    import ssl
    import urllib.error
    import urllib.request

    context = None
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    request = urllib.request.Request(url, data=body, headers=headers,
                                     method=method)
    try:
        with urllib.request.urlopen(request, timeout=60,
                                    context=context) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise SquidmapsError(None, "Couldn't reach squidmaps: {}".format(
            e.reason))
