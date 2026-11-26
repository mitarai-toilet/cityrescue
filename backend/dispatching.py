"""Dispatch integration boundary; no route-finding algorithm is implemented here."""

from copy import deepcopy
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from backend.campus import DEFAULT_DATA, entity_schema, load_campus, read_json
from backend.simulation import FixtureSimulationProvider


class DispatchProvider(Protocol):
    name: str

    def dispatch(self, snapshot: dict, spatial: dict, vehicles: list[dict], events: list[dict]) -> dict: ...


class FixtureDispatchProvider:
    name = 'fixture_dispatch'

    def dispatch(self, snapshot, spatial, vehicles, events):
        canonical = load_campus(DEFAULT_DATA)
        provider = FixtureSimulationProvider(DEFAULT_DATA)
        scenario = next(s for s in provider.scenarios() if s['hazard_type'] == 'flood')
        baseline = provider.replay(scenario).roads
        inputs_match = (spatial == canonical and snapshot['scenario'] == scenario
                        and snapshot['time_min'] == 20 and snapshot['mode'] == 'fixture_replay'
                        and snapshot['data_origin'] == 'synthetic'
                        and vehicles == read_json(DEFAULT_DATA / 'vehicles.json')[:1]
                        and events == read_json(DEFAULT_DATA / 'events.json')[:1])
        # Match the entire effective road snapshot, not merely IDs or the requested route.
        actual = [{k: v for k, v in road.items() if k != 'state_version'} for road in snapshot['roads']]
        baseline = [{k: v for k, v in road.items() if k != 'state_version'} for road in baseline]
        cases = read_json(Path(__file__).parent / 'fixtures' / 'dispatch_cases.json')
        for case in cases:
            expected = deepcopy(baseline)
            if case['manual_closed_road']:
                for road in expected:
                    if road['road_id'] == case['manual_closed_road']:
                        road.update(status='closed', source='manual', reason='Manual closure')
            if inputs_match and actual == expected:
                return {'run_id': snapshot['run_id'], 'state_version': snapshot['state_version'],
                        'assignments': [{'vehicle_id': vehicles[0]['vehicle_id'], 'event_id': events[0]['event_id'],
                                         'road_ids': case['road_ids'], 'eta_min': case['eta_min'], 'outcome': 'assigned'}],
                        'unassigned_events': [], 'outcome': 'complete'}
        raise HTTPException(501, detail={'code': 'dispatch_input_not_supported',
                                        'message': 'No real algorithm installed; input does not match a fixed dispatch case'})


def validate_inputs(spatial, vehicles, events):
    nodes = {node['node_id'] for node in spatial['nodes']}
    if not vehicles or not events:
        raise HTTPException(422, detail={'code': 'empty_dispatch_input'})
    for entity, records in (('vehicle', vehicles), ('event', events)):
        validator = Draft202012Validator(entity_schema(entity))
        try:
            for record in records:
                validator.validate(record)
        except ValidationError as exc:
            raise HTTPException(422, detail={'code': 'invalid_dispatch_input', 'message': exc.message}) from exc
        ids = [r[f'{entity}_id'] for r in records]
        if len(ids) != len(set(ids)) or any(r['node_id'] not in nodes for r in records):
            raise HTTPException(422, detail={'code': 'invalid_dispatch_reference'})


def validate_result(result, snapshot, spatial, vehicles, events):
    def bad():
        raise HTTPException(502, detail={'code': 'invalid_dispatch_provider_result'})

    try:
        Draft202012Validator(entity_schema('dispatch_result')).validate(result)
    except ValidationError:
        bad()
    if result['run_id'] != snapshot['run_id'] or result['state_version'] != snapshot['state_version']:
        bad()
    vehicle_map = {v['vehicle_id']: v for v in vehicles}
    event_map = {e['event_id']: e for e in events}
    road_map = {r['road_id']: r for r in spatial['roads']}
    states = {r['road_id']: r for r in snapshot['roads']}
    used_vehicles, used_events = set(), set()
    for assignment in result['assignments']:
        vid, eid = assignment['vehicle_id'], assignment['event_id']
        if vid not in vehicle_map or eid not in event_map or vid in used_vehicles or eid in used_events:
            bad()
        used_vehicles.add(vid)
        used_events.add(eid)
        if assignment['outcome'] == 'unreachable':
            if assignment['road_ids'] or not assignment.get('reason'):
                bad()
            continue
        if assignment['eta_min'] is None:
            bad()
        node = vehicle_map[vid]['node_id']
        for rid in assignment['road_ids']:
            if rid not in road_map or rid not in states or states[rid]['status'] == 'closed':
                bad()
            road = road_map[rid]
            if node == road['from_node']:
                node = road['to_node']
            elif node == road['to_node'] and not road['one_way']:
                node = road['from_node']
            else:
                bad()
        if node != event_map[eid]['node_id']:
            bad()
    unassigned = result['unassigned_events']
    if len(set(unassigned)) != len(unassigned) or set(unassigned) & used_events or set(unassigned) | used_events != set(event_map):
        bad()
    assigned_count = sum(a['outcome'] == 'assigned' for a in result['assignments'])
    expected_outcome = ('complete' if assigned_count == len(events)
                        else 'unreachable' if assigned_count == 0 else 'partial')
    if result['outcome'] != expected_outcome:
        bad()
