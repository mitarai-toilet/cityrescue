"""Uvicorn entry point with D's route-finding provider installed."""

from backend.app import create_app
from backend.networkx_dispatch import NetworkXDispatchProvider

app = create_app(dispatch_provider=NetworkXDispatchProvider())
