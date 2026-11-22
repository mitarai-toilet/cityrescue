import json
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'data/fixtures/synthetic_campus'; SC=ROOT/'contracts/schemas'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def test_fixed_sample_uses_canonical_v0_1_fields():
 schema=read(ROOT/'contracts/schema_v0_1.json'); sample=read(ROOT/'contracts/sample_v0_1.json')
 Draft202012Validator.check_schema(schema)
 assert sample['contract_version']=='0.1'
 assert 'from_node_id' not in json.dumps(sample) and 'to_node_id' not in json.dumps(sample)
 assert 'risk_cost' not in json.dumps(sample)
 assert sample['campus']['data_origin']=='synthetic'

def test_aggregate_entities_match_canonical_schemas():
 sample=read(ROOT/'contracts/sample_v0_1.json')
 for name in ('campus','node','road','building','scenario','road_state','building_state','vehicle','event','dispatch_result','explain_result'):
  single={'campus','scenario','dispatch_result','explain_result'}
  keys={'node':'nodes','road':'roads','building':'buildings','road_state':'road_states','building_state':'building_states','vehicle':'vehicles','event':'events'}
  values=[sample[name]] if name in single else sample[keys[name]]
  validator=Draft202012Validator(read(SC/(name+'.schema.json')))
  for value in values:
   validator.validate(value)
