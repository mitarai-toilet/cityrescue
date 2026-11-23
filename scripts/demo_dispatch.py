"""Print versioned dispatch results for the fixed flood and earthquake fixtures."""

import json

from backend.campus import DEFAULT_DATA, load_campus, read_json
from backend.integration import IntegrationService
from backend.networkx_dispatch import NetworkXDispatchProvider
from backend.simulation import FixtureSimulationProvider, RunStore


def main():
    spatial = load_campus()
    vehicles = read_json(DEFAULT_DATA / 'vehicles.json')
    events = read_json(DEFAULT_DATA / 'events.json')
    store = RunStore(FixtureSimulationProvider(DEFAULT_DATA))
    service = IntegrationService(store, lambda: spatial, NetworkXDispatchProvider())

    results = {}
    for scenario_id in ('SIM-FLOOD-01', 'SIM-EARTHQUAKE-01'):
        snapshot = store.create(scenario_id)
        run_id, version = snapshot['run_id'], snapshot['state_version']
        before = service.dispatch(run_id, version, vehicles, events)['result']
        first_route = before['assignments'][0]['road_ids']
        closed_road = first_route[0]
        change = store.set_manual_closure(run_id, closed_road, version, True)
        updated_version = change['state_version']
        after = service.dispatch(run_id, updated_version, vehicles, events)['result']
        busy = [dict(vehicle, available_at_min=snapshot['time_min'] + 1) for vehicle in vehicles]
        no_vehicle = service.dispatch(run_id, updated_version, busy, events)['result']
        results[scenario_id] = {
            'data_origin': snapshot['data_origin'], 'closed_road_id': closed_road,
            'before': before, 'after': after, 'no_vehicle': no_vehicle,
        }
    print(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
