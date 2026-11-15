import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_sample_matches_v0_1_contract():
    schema = json.loads((ROOT / "contracts" / "schema_v0_1.json").read_text(encoding="utf-8-sig"))
    sample = json.loads((ROOT / "contracts" / "sample_v0_1.json").read_text(encoding="utf-8-sig"))
    assert schema["$schema"].endswith("2020-12/schema")
    assert sample["contract_version"] == "0.1"
    for key in schema["required"]:
        assert key in sample, f"missing top-level field: {key}"
    assert sample["scenario"]["hazard_type"] in {"flood", "earthquake"}
    assert sample["scenario"]["data_status"] == "synthetic"
    for collection, required in (("roads", {"road_id", "from_node_id", "to_node_id", "length_m", "geometry"}),
                                 ("road_states", {"road_id", "status", "state_version", "reason"}),
                                 ("vehicles", {"vehicle_id", "node_id", "capacity", "status"}),
                                 ("events", {"event_id", "node_id", "event_type", "priority"})):
        assert all(required <= item.keys() for item in sample[collection]), collection
    assert sample["dispatch_result"]["data_status"] == "synthetic"
