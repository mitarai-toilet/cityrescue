from copy import deepcopy
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.campus import DEFAULT_DATA, load_campus, read_json
from backend.dispatching import validate_result
from backend.networkx_dispatch import NetworkXDispatchProvider
from backend.providers import ProviderError
from backend.simulation import FixtureSimulationProvider, RunStore


@pytest.fixture
def context():
    spatial = load_campus()
    snapshot = RunStore(FixtureSimulationProvider(DEFAULT_DATA)).create('SIM-FLOOD-01')
    states = snapshot['roads']
    for state in states:
        state.update(status='open', risk_penalty_min=0)
    return (snapshot, spatial, read_json(DEFAULT_DATA / 'vehicles.json'),
            read_json(DEFAULT_DATA / 'events.json'))


def test_two_vehicles_three_events_deterministic_and_no_mutation(context):
    snapshot, spatial, vehicles, events = context
    original = deepcopy(context)
    provider = NetworkXDispatchProvider()
    result = provider.dispatch(*context)
    validate_result(result, *context)
    assert len(result['assignments']) == 2
    assert result['unassigned_events'] == ['SIM-E3']
    assert len({a['vehicle_id'] for a in result['assignments']}) == 2
    assert [a['event_id'] for a in result['assignments']] == ['SIM-E1', 'SIM-E2']
    assert result == provider.dispatch(snapshot, spatial, list(reversed(vehicles)), list(reversed(events)))
    assert original == context


def test_normal_detour_and_unreachable_with_fixture_roads(context):
    snapshot, spatial, vehicles, events = context
    provider = NetworkXDispatchProvider()
    vehicles, events = vehicles[:1], events[:1]
    before = provider.dispatch(snapshot, spatial, vehicles, events)
    assert before['assignments'][0]['road_ids'] == ['SIM-R01', 'SIM-R02']
    for state in snapshot['roads']:
        if state['road_id'] == 'SIM-R01':
            state.update(status='closed', source='manual')
    after = provider.dispatch(snapshot, spatial, vehicles, events)
    validate_result(after, snapshot, spatial, vehicles, events)
    assert after['assignments'][0]['road_ids'] != before['assignments'][0]['road_ids']
    assert 'SIM-R01' not in after['assignments'][0]['road_ids']
    for state in snapshot['roads']:
        if state['road_id'] in ('SIM-R07', 'SIM-R13'):
            state['status'] = 'closed'
    blocked = provider.dispatch(snapshot, spatial, vehicles, events)
    validate_result(blocked, snapshot, spatial, vehicles, events)
    assert blocked['outcome'] == 'unreachable' and blocked['assignments'] == []
    assert blocked['unassigned_events'] == ['SIM-E1']


def test_risk_is_charged_on_open_roads_and_eta_is_travel_only(context):
    snapshot, spatial, vehicles, events = context
    vehicles, events = vehicles[:1], events[:1]
    for state in snapshot['roads']:
        if state['road_id'] == 'SIM-R01':
            state['risk_penalty_min'] = 100
    result = NetworkXDispatchProvider().dispatch(snapshot, spatial, vehicles, events)
    assignment, = result['assignments']
    assert 'SIM-R01' not in assignment['road_ids']
    roads = {road['road_id']: road for road in spatial['roads']}
    assert assignment['eta_min'] == pytest.approx(sum(
        roads[rid]['length_m'] / roads[rid]['speed_kmh'] * .06 for rid in assignment['road_ids']))
    assert assignment['eta_min'] < 100


def test_availability_capability_and_existing_event_status(context):
    snapshot, spatial, vehicles, events = context
    for vehicle in vehicles:
        vehicle['available_at_min'] = snapshot['time_min'] + 1
    assert NetworkXDispatchProvider().dispatch(*context)['assignments'] == []
    vehicles[0]['available_at_min'] = snapshot['time_min']
    provider = NetworkXDispatchProvider({'SIM-E1': ['missing-capability']})
    result = provider.dispatch(*context)
    assert [a['event_id'] for a in result['assignments']] == ['SIM-E2']
    events[1]['status'] = 'in_progress'
    assert [a['event_id'] for a in provider.dispatch(*context)['assignments']] == ['SIM-E3']


def test_parallel_road_direction_and_zero_distance(context):
    snapshot, spatial, vehicles, events = context
    vehicles, events = deepcopy(vehicles[:1]), deepcopy(events[:1])
    road = deepcopy(next(r for r in spatial['roads'] if r['road_id'] == 'SIM-R01'))
    road.update(road_id='SIM-PARALLEL', speed_kmh=road['speed_kmh'] * 10, one_way=True)
    spatial['roads'].append(road)
    snapshot['roads'].append({**snapshot['roads'][0], 'road_id': road['road_id']})
    events[0]['node_id'] = road['to_node']
    provider = NetworkXDispatchProvider()
    assert provider.dispatch(snapshot, spatial, vehicles, events)['assignments'][0]['road_ids'] == ['SIM-PARALLEL']
    vehicles[0]['node_id'] = road['to_node']
    events[0]['node_id'] = road['from_node']
    reverse = provider.dispatch(snapshot, spatial, vehicles, events)['assignments'][0]
    assert 'SIM-PARALLEL' not in reverse['road_ids']
    events[0]['node_id'] = vehicles[0]['node_id']
    same = provider.dispatch(snapshot, spatial, vehicles, events)['assignments'][0]
    assert same['road_ids'] == [] and same['eta_min'] == 0


@pytest.mark.parametrize('invalid', ['duplicate', 'missing_state', 'version', 'node'])
def test_bad_inputs_use_provider_boundary(context, invalid):
    snapshot, spatial, vehicles, events = context
    if invalid == 'duplicate':
        vehicles.append(deepcopy(vehicles[0]))
    elif invalid == 'missing_state':
        snapshot['roads'].pop()
    elif invalid == 'version':
        snapshot['roads'][0]['state_version'] += 1
    else:
        events[0]['node_id'] = 'missing'
    with pytest.raises(ProviderError) as exc:
        NetworkXDispatchProvider().dispatch(*context)
    assert exc.value.status == 400


@pytest.mark.parametrize('scenario', ['SIM-FLOOD-01', 'SIM-EARTHQUAKE-01'])
def test_api_both_hazards_and_closure_versions(scenario):
    app = create_app(dispatch_provider=NetworkXDispatchProvider())
    with TestClient(app) as client:
        response = client.post('/api/v1/simulation/runs', json={'scenario_id': scenario})
        assert response.status_code == 201, response.text
        run = response.json()
        body = {'run_id': run['run_id'], 'state_version': 0,
                'vehicles': read_json(DEFAULT_DATA / 'vehicles.json'),
                'events': read_json(DEFAULT_DATA / 'events.json')}
        first = client.post('/api/v1/dispatch', json=body)
        assert first.status_code == 200, first.text
        chosen = first.json()['result']['assignments'][0]['road_ids'][0]
        root = '/api/v1/simulation/runs/' + run['run_id']
        assert client.post(root + f'/roads/{chosen}/close', json={'state_version': 0}).status_code == 200
        assert client.post('/api/v1/dispatch', json=body).status_code == 409
        body['state_version'] = 1
        updated = client.post('/api/v1/dispatch', json=body)
        assert updated.status_code == 200, updated.text
        assert updated.json()['result']['state_version'] == 1
        assert all(chosen not in a['road_ids'] for a in updated.json()['result']['assignments'])
        assert len(client.get(root + '/history').json()['dispatches']) == 2


def test_real_provider_result_rejected_after_concurrent_closure():
    started, release = Event(), Event()

    class Delayed(NetworkXDispatchProvider):
        def dispatch(self, *args):
            result = super().dispatch(*args)
            started.set()
            assert release.wait(5)
            return result

    app = create_app(dispatch_provider=Delayed())
    with TestClient(app) as client:
        run = app.state.simulation_runs.create('SIM-FLOOD-01')['run_id']
        body = {'run_id': run, 'state_version': 0,
                'vehicles': read_json(DEFAULT_DATA / 'vehicles.json'),
                'events': read_json(DEFAULT_DATA / 'events.json')}
        responses = []
        thread = Thread(target=lambda: responses.append(client.post('/api/v1/dispatch', json=body)))
        thread.start()
        try:
            assert started.wait(5)
            app.state.simulation_runs.set_manual_closure(run, 'SIM-R01', 0, True)
        finally:
            release.set()
            thread.join(10)
        assert not thread.is_alive()
        assert responses[0].status_code == 409
        assert app.state.simulation_runs.history(run)['dispatches'] == []
