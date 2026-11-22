import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'data/fixtures/synthetic_campus'
SCHEMAS=ROOT/'contracts/schemas'

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))

def test_all_entity_schemas_are_draft_2020_12_and_valid():
    for path in sorted(SCHEMAS.glob('*.schema.json')):
        schema=load(path)
        assert schema['$schema']=='https://json-schema.org/draft/2020-12/schema', path.name
        Draft202012Validator.check_schema(schema)

def samples():
    campus=load(FIX/'campus.json')
    nodes=load(FIX/'nodes.geojson')['features']
    roads=load(FIX/'roads.geojson')['features']
    buildings=load(FIX/'buildings.geojson')['features']
    return {
      'campus':campus,
      'node':{'node_id':nodes[0]['properties']['node_id'],'position':nodes[0]['geometry']},
      'road':{**roads[0]['properties'],'geometry':roads[0]['geometry']},
      'building':{**buildings[0]['properties'],'geometry':buildings[0]['geometry']},
      'scenario':load(FIX/'flood_scenario.json'),
      'road_state':load(FIX/'road_states.json')[0],
      'building_state':load(FIX/'building_states.json')[0],
      'vehicle':load(FIX/'vehicles.json')[0],
      'event':load(FIX/'events.json')[0],
      'dispatch_result':{'run_id':'SIM-RUN-01','state_version':1,'assignments':[{'event_id':'SIM-E1','vehicle_id':'SIM-V1','road_ids':['SIM-R01'],'eta_min':2,'outcome':'assigned'}],'unassigned_events':[],'outcome':'complete'},
      'explain_result':{'run_id':'SIM-RUN-01','state_version':1,'summary':'合成测试解释','evidence_ids':['SIM-R01'],'limitations':['合成数据']},
    }

def test_valid_example_for_every_entity():
    for entity,sample in samples().items():
        schema=load(SCHEMAS/f'{entity}.schema.json')
        errors=list(Draft202012Validator(schema).iter_errors(sample))
        assert not errors, f'{entity}: {[e.message for e in errors]}'

@pytest.mark.parametrize('entity,mutator',[
 ('campus',lambda x:x.pop('campus_id')),
 ('road',lambda x:x.update(length_m='long')),
 ('road_state',lambda x:x.update(status='blocked')),
 ('event',lambda x:x.update(priority=0)),
])
def test_invalid_examples_are_rejected(entity,mutator):
    sample=samples()[entity]
    mutator(sample)
    validator=Draft202012Validator(load(SCHEMAS/f'{entity}.schema.json'))
    assert not validator.is_valid(sample)


def test_all_fixture_entities_and_aggregate_offline():
    resources = []
    for path in SCHEMAS.glob('*.schema.json'):
        resources.append(('https://cityrescue.local/contracts/schemas/' + path.name,
                          Resource.from_contents(load(path))))
    registry = Registry().with_resources(resources)
    aggregate = load(ROOT / 'contracts/schema_v0_1.json')
    Draft202012Validator.check_schema(aggregate)
    Draft202012Validator(aggregate, registry=registry).validate(
        load(ROOT / 'contracts/sample_v0_1.json'))
    collections = {
        'campus': [load(FIX / 'campus.json')],
        'node': [{'node_id': f['properties']['node_id'], 'position': f['geometry']}
                 for f in load(FIX / 'nodes.geojson')['features']],
        'road': [{**f['properties'], 'geometry': f['geometry']}
                 for f in load(FIX / 'roads.geojson')['features']],
        'building': [{**f['properties'], 'geometry': f['geometry']}
                     for f in load(FIX / 'buildings.geojson')['features']],
        'scenario': [load(FIX / 'flood_scenario.json'), load(FIX / 'earthquake_scenario.json')],
        'road_state': load(FIX / 'road_states.json'),
        'building_state': load(FIX / 'building_states.json'),
        'vehicle': load(FIX / 'vehicles.json'), 'event': load(FIX / 'events.json'),
    }
    snapshots = load(FIX / 'manual_closure_snapshots.json')
    for label in ('before', 'after'):
        snapshot = snapshots[label]
        for state in snapshot['road_states']:
            collections['road_state'].append({**state, 'time_min': snapshot['time_min']})
    for entity, records in collections.items():
        validator = Draft202012Validator(load(SCHEMAS / f'{entity}.schema.json'))
        for record in records:
            validator.validate(record)
    for path in list((ROOT / 'contracts').rglob('*.json')) + list(FIX.glob('*.json')) + list(FIX.glob('*.geojson')):
        load(path)


@pytest.mark.parametrize('entity', sorted(samples()))
def test_required_fields_types_and_enums_rejected_for_every_entity(entity):
    schema = load(SCHEMAS / f'{entity}.schema.json')
    validator = Draft202012Validator(schema)
    for field in schema['required']:
        invalid = deepcopy(samples()[entity])
        del invalid[field]
        assert not validator.is_valid(invalid), (entity, field)
    for field, spec in schema['properties'].items():
        invalid = deepcopy(samples()[entity])
        invalid[field] = '__INVALID_ENUM__' if 'enum' in spec or 'const' in spec or spec.get('type') == 'boolean' else False
        assert not validator.is_valid(invalid), (entity, field)
