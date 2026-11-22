import json
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from jsonschema import Draft202012Validator

from backend.campus import DEFAULT_DATA, CampusDataError, entity_schema
from backend.simulation import FixtureSimulationProvider, RunStore
from backend.app import create_app
from test_campus_api import server


def test_simulation_http_queries_versions_and_isolation():
    with server(DEFAULT_DATA) as request:
        openapi = request('/openapi.json')[1]
        status, scenarios = request('/api/v1/scenarios')
        assert status == 200 and len(scenarios) == 2
        runs = []
        for scenario in scenarios:
            sid = scenario['scenario_id']
            assert request('/api/v1/scenarios/' + sid) == (200, scenario)
            status, run = request('/api/v1/simulation/runs', {'scenario_id': sid, 'params': scenario['params']})
            assert status == 201 and run['state_version'] == 0
            schema = openapi['paths']['/api/v1/simulation/runs']['post']['responses']['201']['content']['application/json']['schema']
            Draft202012Validator(schema).validate(run)
            assert run['mode'] == 'fixture_replay' and run['data_origin'] == 'synthetic'
            path = '/api/v1/simulation/runs/' + run['run_id']
            assert request(path) == (200, run)
            status, snapshot = request(path + '/state')
            assert status == 200 and snapshot['time_min'] == 20
            schema = openapi['paths']['/api/v1/simulation/runs/{run_id}/state']['get']['responses']['200']['content']['application/json']['schema']
            Draft202012Validator(schema).validate(snapshot)
            assert request(path + '/state') == (200, snapshot)
            roads = request(path + '/roads')[1]
            buildings = request(path + '/buildings')[1]
            assert len(roads) == 16 and roads == snapshot['roads'] and buildings == snapshot['buildings']
            for entity, records in (('road_state', roads), ('building_state', buildings)):
                validator = Draft202012Validator(entity_schema(entity))
                for record in records:
                    validator.validate(record)
            assert all(r['state_version'] == snapshot['state_version'] for r in roads)
            if scenario['hazard_type'] == 'flood':
                assert buildings == []
                assert {r['road_id'] for r in roads if r['status'] == 'closed'} == {'SIM-R09'}
            else:
                assert len(buildings) == 5
                assert {r['road_id'] for r in roads if r['status'] == 'closed'} == set(scenario['params']['affected_road_ids'])
                assert all(r['depth_m'] is None for r in roads)
            runs.append((path, snapshot))
        assert runs[0][1]['run_id'] != runs[1][1]['run_id']
        assert request(runs[0][0] + '/state') == (200, runs[0][1])
        status, third = request('/api/v1/simulation/runs', {'scenario_id': scenarios[0]['scenario_id']})
        assert status == 201 and third['run_id'] not in {r[1]['run_id'] for r in runs}
        assert third['state_version'] == 0
        assert request('/api/v1/scenarios/absent')[0] == 404
        assert request('/api/v1/simulation/runs', {'scenario_id': 'absent'})[0] == 404
        for suffix in ('', '/roads', '/buildings', '/state'):
            assert request('/api/v1/simulation/runs/absent' + suffix)[0] == 404
        assert request('/api/v1/simulation/runs', {'scenario_id': scenarios[0]['scenario_id'], 'params': {}})[0] == 422
        assert request('/api/v1/simulation/runs', {'scenario_id': scenarios[0]['scenario_id'], 'seed': 999})[0] == 422
        assert request('/api/v1/campus')[0] == 200


@pytest.mark.parametrize('corruption', ['missing', 'json', 'reference', 'duplicate', 'building'])
def test_bad_fixture_http_error(tmp_path, corruption):
    directory = tmp_path / 'fixture'
    shutil.copytree(DEFAULT_DATA, directory)
    filename = 'building_states.json' if corruption == 'building' else 'road_states.json'
    path = directory / filename
    if corruption == 'missing':
        path.unlink()
    elif corruption == 'json':
        path.write_text('{broken', encoding='utf-8')
    else:
        data = json.loads(path.read_text(encoding='utf-8'))
        if corruption == 'duplicate':
            data.append(data[0])
        elif corruption == 'reference':
            data[0]['road_id'] = 'missing-road'
        else:
            data[0]['building_id'] = 'missing-building'
        path.write_text(json.dumps(data), encoding='utf-8')
    with server(directory) as request:
        sid = 'SIM-EARTHQUAKE-01' if corruption == 'building' else 'SIM-FLOOD-01'
        status, result = request('/api/v1/simulation/runs', {'scenario_id': sid})
        assert status == 503 and result['detail']['code'] in {'data_file_missing', 'invalid_json', 'invalid_simulation_data'}
        assert request('/api/v1/campus')[0] == 200


def test_run_store_defensive_copies_concurrent_creation_and_restart():
    store = RunStore(FixtureSimulationProvider(DEFAULT_DATA))
    with ThreadPoolExecutor(max_workers=4) as executor:
        runs = list(executor.map(lambda _: store.create('SIM-FLOOD-01'), range(8)))
    assert len({run['run_id'] for run in runs}) == 8
    run = runs[0]
    run['roads'][0]['status'] = 'closed'
    run['scenario']['params'].clear()
    saved = store.get(run['run_id'])
    assert saved['roads'][0]['status'] == 'open' and saved['scenario']['params']
    with pytest.raises(HTTPException) as exc:
        RunStore(FixtureSimulationProvider(DEFAULT_DATA)).get(run['run_id'])
    assert exc.value.status_code == 404


def test_bad_scenario_does_not_publish_run(tmp_path):
    shutil.copytree(DEFAULT_DATA, tmp_path / 'fixture')
    directory = tmp_path / 'fixture'
    path = directory / 'flood_scenario.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    record['campus_id'] = 'missing-campus'
    path.write_text(json.dumps(record), encoding='utf-8')
    store = RunStore(FixtureSimulationProvider(directory))
    with pytest.raises(CampusDataError):
        store.create('SIM-FLOOD-01')
    assert store._runs == {}


def test_provider_injection_and_inconsistent_snapshot_rejection():
    class Provider:
        def __init__(self):
            self.fixture = FixtureSimulationProvider(DEFAULT_DATA)
            self.bad = False

        def scenarios(self):
            return self.fixture.scenarios()

        def replay(self, scenario):
            snapshot = self.fixture.replay(scenario)
            if self.bad:
                snapshot.roads[0]['time_min'] = 30
            return snapshot

    provider = Provider()
    store = create_app(simulation_provider=provider).state.simulation_runs
    first = store.create('SIM-FLOOD-01')
    provider.bad = True
    with pytest.raises(CampusDataError, match='inconsistent'):
        store.create('SIM-FLOOD-01')
    assert list(store._runs) == [first['run_id']]
    assert store.get(first['run_id']) == first
