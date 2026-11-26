from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.campus import DEFAULT_DATA, entity_schema, load_campus, read_json
from backend.dispatching import FixtureDispatchProvider, validate_result
from backend.simulation import FixtureSimulationProvider, RunStore
from test_campus_api import server


def inputs(run_id, version=0):
    return {'run_id': run_id, 'state_version': version,
            'vehicles': read_json(DEFAULT_DATA / 'vehicles.json')[:1],
            'events': read_json(DEFAULT_DATA / 'events.json')[:1]}


def test_real_http_closure_version_dispatch_chain():
    with server(DEFAULT_DATA) as request:
        def create():
            status, run = request('/api/v1/simulation/runs', {'scenario_id': 'SIM-FLOOD-01'})
            assert status == 201
            return run['run_id']

        rid, other = create(), create()
        root = '/api/v1/simulation/runs/' + rid
        status, initial = request('/api/v1/dispatch', inputs(rid))
        assert status == 200 and initial['provider'] == 'fixture_dispatch'
        assert initial['result']['assignments'][0]['road_ids'] == ['SIM-R01', 'SIM-R02']
        status, change = request(root + '/roads/SIM-R01/close', {'state_version': 0})
        assert status == 200 and change['changed'] and change['state_version'] == 1
        assert change['road']['status'] == 'closed' and change['road']['source'] == 'manual'
        status, stale = request(root + '/roads/SIM-R02/close', {'state_version': 0})
        assert status == 409 and stale['detail']['current_state_version'] == 1
        assert request(root + '/roads/SIM-R01/close', {'state_version': 1})[1]['changed'] is False
        assert request(root + '/state')[1]['state_version'] == 1
        assert request('/api/v1/dispatch', inputs(rid, 0))[0] == 409
        status, rerun = request('/api/v1/dispatch', inputs(rid, 1))
        assert status == 200 and rerun['result']['state_version'] == 1
        assert rerun['result']['assignments'][0]['road_ids'] == ['SIM-R07', 'SIM-R03', 'SIM-R15']
        Draft202012Validator(entity_schema('dispatch_result')).validate(rerun['result'])
        assert request('/api/v1/simulation/runs/' + other + '/state')[1]['state_version'] == 0
        assert request(root + '/roads/SIM-R01/open', {'state_version': 1})[1]['state_version'] == 2
        assert request(root + '/roads/SIM-R01/open', {'state_version': 2})[1]['changed'] is False
        assert request('/api/v1/dispatch', inputs(rid, 2))[0] == 200
        assert request(root + '/roads/absent/close', {'state_version': 2})[0] == 404
        assert request('/api/v1/simulation/runs/absent/roads/SIM-R01/close', {'state_version': 0})[0] == 404
        assert request(root + '/roads/SIM-R01/close', {})[0] == 422
        assert request(root + '/roads/SIM-R01/close', {'state_version': True})[0] == 422
        history = request(root + '/history')[1]
        assert len(history['changes']) == 2 and len(history['dispatches']) == 3
        assert [d['result']['state_version'] for d in history['dispatches']] == [0, 1, 2]
        # A second closure pattern is not a licensed fixed dispatch case.
        assert request(root + '/roads/SIM-R02/close', {'state_version': 2})[1]['state_version'] == 3
        assert request('/api/v1/dispatch', inputs(rid, 3))[0] == 501


def test_disaster_closure_survives_manual_reopen_and_histories_are_isolated():
    store = RunStore(FixtureSimulationProvider(DEFAULT_DATA))
    run = store.create('SIM-FLOOD-01')['run_id']
    other = store.create('SIM-FLOOD-01')['run_id']
    before = store.get(run)
    store.set_manual_closure(run, 'SIM-R09', 0, True)
    result = store.set_manual_closure(run, 'SIM-R09', 1, False)
    assert result['road']['status'] == 'closed' and result['road']['source'] == 'hazard'
    assert result['state_version'] == 2 and not result['manual_closed']
    assert store.get(other)['state_version'] == 0 and store.history(other)['changes'] == []
    assert before['roads'][0]['state_version'] == 0
    assert all(r['state_version'] == 2 for r in store.get(run)['roads'])


def test_same_old_version_concurrent_changes_have_one_winner():
    store = RunStore(FixtureSimulationProvider(DEFAULT_DATA))
    run = store.create('SIM-FLOOD-01')['run_id']

    def close(road):
        try:
            store.set_manual_closure(run, road, 0, True)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(close, ['SIM-R01', 'SIM-R02']))
    assert sorted(codes) == [200, 409]
    assert store.get(run)['state_version'] == 1
    assert len(store.history(run)['changes']) == 1


@pytest.mark.parametrize('bad', ['node', 'duplicate', 'schema', 'unsupported', 'unknown_run'])
def test_dispatch_rejects_invalid_or_unmatched_inputs(bad):
    app = create_app()
    with TestClient(app) as client:
        run = client.post('/api/v1/simulation/runs', json={'scenario_id': 'SIM-FLOOD-01'}).json()['run_id']
        body = inputs(run)
        if bad == 'node':
            body['events'][0]['node_id'] = 'missing'
        elif bad == 'duplicate':
            body['events'].append(deepcopy(body['events'][0]))
        elif bad == 'schema':
            body['events'][0]['priority'] = 0
        elif bad == 'unsupported':
            body['vehicles'][0]['available_at_min'] = 1
        else:
            body['run_id'] = 'missing'
        response = client.post('/api/v1/dispatch', json=body)
        assert response.status_code == (501 if bad == 'unsupported' else 404 if bad == 'unknown_run' else 422)
        assert app.state.simulation_runs.history(run)['dispatches'] == []


def test_dispatch_detects_state_change_during_provider_execution():
    fixture = FixtureDispatchProvider()

    class RacingProvider:
        name = 'race-test'

        def dispatch(self, snapshot, spatial, vehicles, events):
            result = fixture.dispatch(snapshot, spatial, vehicles, events)
            app.state.simulation_runs.set_manual_closure(snapshot['run_id'], 'SIM-R01', 0, True)
            return result

    app = create_app(dispatch_provider=RacingProvider())
    with TestClient(app) as client:
        run = app.state.simulation_runs.create('SIM-FLOOD-01')['run_id']
        response = client.post('/api/v1/dispatch', json=inputs(run))
        assert response.status_code == 409
        assert app.state.simulation_runs.history(run)['dispatches'] == []


@pytest.mark.parametrize('bad', ['closed', 'direction', 'version', 'missing_task', 'outcome'])
def test_bad_provider_result_is_rejected(bad):
    store = RunStore(FixtureSimulationProvider(DEFAULT_DATA))
    snapshot = store.create('SIM-FLOOD-01')
    request = inputs(snapshot['run_id'])
    spatial = load_campus()
    result = FixtureDispatchProvider().dispatch(snapshot, spatial, request['vehicles'], request['events'])
    if bad == 'closed':
        result['assignments'][0]['road_ids'] = ['SIM-R09']
    elif bad == 'direction':
        spatial['roads'][0]['one_way'] = True
        spatial['roads'][0]['from_node'], spatial['roads'][0]['to_node'] = spatial['roads'][0]['to_node'], spatial['roads'][0]['from_node']
    elif bad == 'version':
        result['state_version'] = 99
    elif bad == 'outcome':
        result['outcome'] = 'partial'
    else:
        result['assignments'] = []
    with pytest.raises(HTTPException) as exc:
        validate_result(result, snapshot, spatial, request['vehicles'], request['events'])
    assert exc.value.status_code == 502
