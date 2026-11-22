import json
from pathlib import Path
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "synthetic_campus"


def read(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8-sig"))


def test_fixture_integrity_and_references():
    campus = read("campus.json")
    nodes = read("nodes.geojson")["features"]
    roads = read("roads.geojson")["features"]
    buildings = read("buildings.geojson")["features"]
    node_ids = [f["properties"]["node_id"] for f in nodes]
    road_ids = [f["properties"]["road_id"] for f in roads]
    building_ids = [f["properties"]["building_id"] for f in buildings]
    assert campus["data_origin"] == "synthetic" and not campus["verified"]
    assert len(node_ids) == len(set(node_ids)) and 8 <= len(node_ids) <= 12
    assert len(road_ids) == len(set(road_ids)) and 12 <= len(road_ids) <= 18
    assert len(building_ids) == len(set(building_ids)) and 4 <= len(building_ids) <= 6
    for feature in nodes:
        lon, lat = feature["geometry"]["coordinates"]
        assert -180 <= lon <= 180 and -90 <= lat <= 90
    for feature in roads:
        p = feature["properties"]
        assert p["from_node"] in node_ids and p["to_node"] in node_ids
        assert p["length_m"] > 0 and p["speed_kmh"] > 0
        assert feature["geometry"]["type"] == "LineString"
        assert all(-180 <= c[0] <= 180 and -90 <= c[1] <= 90 for c in feature["geometry"]["coordinates"])
    vehicles, events = read("vehicles.json"), read("events.json")
    assert len(vehicles) == 2 and len(events) == 3
    assert all(v["node_id"] in node_ids for v in vehicles)
    assert all(e["node_id"] in node_ids and 1 <= e["priority"] <= 5 for e in events)
    assert len({v["vehicle_id"] for v in vehicles}) == len(vehicles)
    assert len({e["event_id"] for e in events}) == len(events)
    for name in ("flood_scenario.json", "earthquake_scenario.json"):
        scenario = read(name)
        assert scenario["campus_id"] == campus["campus_id"]
        assert scenario["hazard_type"] in {"flood", "earthquake"}
    buildings_states = read("building_states.json")
    assert all(s["building_id"] in building_ids for s in buildings_states)
    for state in read("road_states.json"):
        assert state["road_id"] in road_ids and state["status"] in {"open", "caution", "closed"}
        assert state["depth_m"] is None or state["depth_m"] >= 0
        assert state["state_version"] >= 0


def _graph(closed=()):
    graph = nx.DiGraph()
    graph.add_nodes_from(f["properties"]["node_id"] for f in read("nodes.geojson")["features"])
    for f in read("roads.geojson")["features"]:
        p = f["properties"]
        if p["road_id"] in closed:
            continue
        graph.add_edge(p["from_node"], p["to_node"], road_id=p["road_id"])
        if not p["one_way"]:
            graph.add_edge(p["to_node"], p["from_node"], road_id=p["road_id"])
    return graph


def test_scenario_connectivity_and_detours():
    expected = read("expected_routes.json")["scenarios"]
    normal = _graph()
    assert nx.has_path(normal, expected["normal"]["from"], expected["normal"]["to"])
    flood = _graph(expected["flood_detour"]["closed_roads"])
    route = nx.shortest_path(flood, expected["flood_detour"]["from"], expected["flood_detour"]["to"])
    chosen_roads = {flood[a][b]["road_id"] for a,b in zip(route,route[1:])}
    assert nx.has_path(flood, expected["flood_detour"]["from"], expected["flood_detour"]["to"])
    assert not set(expected["flood_detour"]["closed_roads"]) & chosen_roads
    earth = _graph(expected["earthquake_block"]["closed_roads"])
    assert nx.has_path(earth, "SIM-N1", "SIM-N3")
    disconnected = _graph(expected["fully_unreachable"]["closed_roads"])
    assert not nx.has_path(disconnected, expected["fully_unreachable"]["from"], expected["fully_unreachable"]["to"])
    for source,target in [("SIM-N1","SIM-N3"),("SIM-N1","SIM-N8")]:
        assert nx.shortest_path(normal,source,target) == nx.shortest_path(normal,source,target)


def test_manual_closure_versions_increase():
    snapshots=read("manual_closure_snapshots.json")
    assert snapshots["after"]["state_version"] > snapshots["before"]["state_version"]
    assert snapshots["before"]["road_states"][0]["status"] == "open"
    assert snapshots["after"]["road_states"][0]["status"] == "closed"


def test_closures_change_paths_and_preserve_snapshot_identity():
    roads = {f['properties']['road_id']: f['properties'] for f in read('roads.geojson')['features']}
    normal = _graph()
    # Verify actual affected endpoints, rather than only checking that some path exists.
    for closed in (['SIM-R09'], read('earthquake_scenario.json')['params']['affected_road_ids']):
        graph = _graph(closed)
        for a, b, attrs in graph.edges(data=True):
            assert attrs['road_id'] not in closed
            road = roads[attrs['road_id']]
            assert (a, b) == (road['from_node'], road['to_node']) or not road['one_way']
        road = roads[closed[0]]
        start, end = road['from_node'], road['to_node']
        assert nx.shortest_path(normal, start, end) != nx.shortest_path(graph, start, end)
    states = read('road_states.json')
    keys = [(s['state_version'], s['time_min'], s['road_id']) for s in states]
    assert len(keys) == len(set(keys))
    scenario = read('flood_scenario.json')
    assert {s['time_min'] for s in states} == set(range(0, scenario['duration_min'] + 1, scenario['step_min']))
    snapshots = read('manual_closure_snapshots.json')
    for label in ('before', 'after'):
        snapshot = snapshots[label]
        for state in snapshot['road_states']:
            assert state['road_id'] in roads
            assert state['state_version'] == snapshot['state_version']


