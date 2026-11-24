import pytest
from fastapi.testclient import TestClient

from backend.campus import read_json
from backend.sipailou_app import SIPAILOU_DATA, app


def test_sipailou_dispatch_uses_osm_road_ids_and_detours():
    with TestClient(app) as client:
        graph = client.get('/api/v1/campus/graph').json()
        assert graph['campus']['campus_id'] == 'SEU-SIPAILOU-OSM'
        assert graph['campus']['data_origin'] == 'real' and graph['campus']['verified'] is False
        assert 'OpenStreetMap contributors' in graph['campus']['data_source']
        roads = {r['road_id']: r for r in graph['roads']}
        assert len(roads) == 50

        run = client.post('/api/v1/simulation/runs', json={'scenario_id': 'SPL-FLOOD-DEMO'})
        assert run.status_code == 201, run.text
        run = run.json()
        assert run['data_origin'] == 'synthetic'
        vehicles = read_json(SIPAILOU_DATA / 'vehicles.json')
        events = read_json(SIPAILOU_DATA / 'events.json')
        body = {'run_id': run['run_id'], 'state_version': 0, 'vehicles': vehicles[:1], 'events': events[:1]}
        first = client.post('/api/v1/dispatch', json=body)
        assert first.status_code == 200, first.text
        baseline, = first.json()['result']['assignments']
        closed = 'SPL-R237022770-2449059357-2450052111'
        assert closed in baseline['road_ids']

        root = '/api/v1/simulation/runs/' + run['run_id']
        assert client.post(f'{root}/roads/{closed}/close', json={'state_version': 0}).status_code == 200
        assert client.post('/api/v1/dispatch', json=body).status_code == 409
        body['state_version'] = 1
        updated = client.post('/api/v1/dispatch', json=body)
        assert updated.status_code == 200, updated.text
        detour, = updated.json()['result']['assignments']
        assert closed not in detour['road_ids']
        assert detour['eta_min'] > baseline['eta_min']
        for assignment in (baseline, detour):
            expected = sum(roads[rid]['length_m'] / roads[rid]['speed_kmh'] * .06
                           for rid in assignment['road_ids'])
            assert assignment['eta_min'] == pytest.approx(expected)

        body.update(vehicles=vehicles, events=events)
        batch = client.post('/api/v1/dispatch', json=body)
        assert batch.status_code == 200, batch.text
        assignments = batch.json()['result']['assignments']
        assert len({a['vehicle_id'] for a in assignments}) == len(assignments) == 2
        assert batch.json()['result']['unassigned_events'] == ['SPL-E3']
