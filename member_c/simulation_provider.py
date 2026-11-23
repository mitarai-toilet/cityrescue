"""Standalone member C provider, pending team protocol signature review."""
from hazard import simulate


class SimulationProvider:
    def simulate(self, scenario, roads, buildings):
        return simulate(scenario, roads, buildings)
