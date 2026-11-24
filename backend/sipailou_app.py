"""Serve the OSM-based SEU Sipailou demo using canonical dispatch entities."""

from backend.app import create_app
from backend.campus import ROOT
from backend.networkx_dispatch import NetworkXDispatchProvider

SIPAILOU_DATA = ROOT / 'data' / 'fixtures' / 'seu_sipailou_osm'

app = create_app(SIPAILOU_DATA, dispatch_provider=NetworkXDispatchProvider())
