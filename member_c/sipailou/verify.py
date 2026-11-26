"""Run standalone checks. Add --backend with the cityrescue repository on PYTHONPATH."""
import json
import sys
from pathlib import Path
from hazard import simulate

root = Path(__file__).resolve().parent
def read(name):
    return json.loads((root / name).read_text(encoding="utf8"))

case = read("detour.json")
for hazard in ("flood", "earthquake"):
    payload = read(hazard + ".input.json")
    frames = read(hazard + ".output.json")
    assert frames == simulate(**payload) == simulate(**payload)
    roads = {r["road_id"]: r for r in payload["roads"]}
    assert [f["time_min"] for f in frames] == list(range(0, 61, 10))
    states = {s["road_id"]: s for s in frames[5]["road_states"]}
    assert states[case["closed_road_id"]]["status"] == "closed"
    node = case["from_node"]
    for key in case["alternative_road_ids"]:
        road = roads[key]
        assert states[key]["status"] != "closed"
        if road["from_node"] == node:
            node = road["to_node"]
        else:
            assert not road["one_way"] and road["to_node"] == node
            node = road["from_node"]
    assert node == case["to_node"]
    if "--backend" in sys.argv:
        from backend.app import create_app
        from backend.c_hazard import CProvider
        from backend.simulation import validate
        d = root / "spl_campus"
        store = create_app(data_directory=d, simulation_provider=CProvider(d)).state.simulation_runs
        for f in frames:
            validate("road_state", f["road_states"])
            validate("building_state", f["building_states"])
        run = store.create(payload["scenario"]["scenario_id"])
        assert run["time_min"] == 60 and len(run["roads"]) == len(roads)
        assert run["buildings"] == frames[-1]["building_states"]
    print(hazard, "PASS", len(roads), "roads,", len(frames), "frames")
