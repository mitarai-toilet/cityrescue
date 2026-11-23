import json
import unittest
from collections import deque
from pathlib import Path

from hazard import simulate

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def flood(**params):
    data = read("fixed_flood.input.json")
    data["scenario"]["params"].update(params)
    return simulate(**data)


def path(roads, frame):
    """Independent D-style consumer: join by ID, remove closed roads, check reachability."""
    states = {s["road_id"]: s for s in frame["road_states"]}
    graph = {}
    for r in roads:
        key = r["road_id"]
        if states[key]["status"] == "closed":
            continue
        a, b = r["from_node"], r["to_node"]
        graph.setdefault(a, []).append((b, key))
        if not r["one_way"]:
            graph.setdefault(b, []).append((a, key))
    queue = deque([("SIM-N1", [])])
    seen = {"SIM-N1"}
    while queue:
        node, route = queue.popleft()
        if node == "SIM-N4":
            return route
        for other, road in graph.get(node, []):
            if other not in seen:
                seen.add(other)
                queue.append((other, route + [road]))
    return None


class Acceptance(unittest.TestCase):
    def test_snapshots_and_reproducibility(self):
        for name in ("fixed_flood", "fixed_quake"):
            data = read(name + ".input.json")
            expected = read(name + ".output.json")
            for attempt in range(3):
                self.assertEqual(simulate(**data), expected)
            data["roads"].reverse()
            self.assertEqual(simulate(**data), expected)

    def test_timeline_and_contract(self):
        frames = flood()
        self.assertEqual([f["time_min"] for f in frames], list(range(0, 61, 10)))
        for index, f in enumerate(frames):
            self.assertEqual(len(f["road_states"]), 4)
            for s in f["road_states"]:
                self.assertEqual(set(s), set("road_id time_min status depth_m risk_penalty_min reason source state_version".split()))
                self.assertEqual(s["time_min"], f["time_min"])
                self.assertEqual(s["state_version"], index)
                self.assertGreaterEqual(s["depth_m"], 0)
                self.assertIn(s["status"], ("open", "caution", "closed"))
            self.assertEqual(set(f["building_states"][0]), set("building_id time_min risk_level reason".split()))
        self.assertEqual(frames[-1]["building_states"][0]["risk_level"], "high")

    def test_zero_and_heavy_rain(self):
        for s in flood(rainfall_mm_h=0)[-1]["road_states"]:
            self.assertEqual((s["depth_m"], s["status"]), (0, "open"))
        self.assertTrue(all(s["status"] == "closed" for s in flood(rainfall_mm_h=1000)[-1]["road_states"]))

    def test_threshold_equality(self):
        frames = flood(rainfall_mm_h=600, catchment_factor={}, drain_mm_h=0)
        self.assertEqual(frames[1]["road_states"][0]["status"], "caution")
        self.assertEqual(frames[3]["road_states"][0]["status"], "closed")

    def test_invalid_parameters(self):
        for params in ({"rainfall_mm_h": -1}, {"rainfall_mm_h": True}, {"rainfall_mm_h": float("nan")},
                       {"closure_depth_m": .1}, {"catchment_factor": {"missing": 2}}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                flood(**params)
        for key, value in (("step_min", 0), ("duration_min", -1), ("seed", 1.5)):
            data = read("fixed_flood.input.json")
            data["scenario"][key] = value
            with self.assertRaises(ValueError):
                simulate(**data)

    def test_partial_step(self):
        data = read("fixed_flood.input.json")
        data["scenario"]["duration_min"] = 14
        self.assertEqual([f["time_min"] for f in simulate(**data)], [0, 10, 14])

    def test_dispatch_consumption(self):
        roads = read("fixed_flood.input.json")["roads"]
        frames = flood()
        self.assertEqual(path(roads, frames[0]), ["SIM-R01", "SIM-R09"])
        self.assertEqual(path(roads, frames[-1]), ["SIM-R07", "SIM-R14"])
        manual = flood(manual_closed_from_min={"SIM-R14": 60})[-1]
        self.assertEqual(manual["road_states"][-1]["source"], "manual")
        self.assertIsNone(path(roads, manual))

    def test_quake_and_invalid_zone(self):
        data = read("fixed_quake.input.json")
        frame = simulate(**data)[0]
        self.assertEqual({s["road_id"] for s in frame["road_states"] if s["status"] == "closed"},
                         {"SIM-R09", "SIM-R14"})
        self.assertTrue(all(s["depth_m"] is None for s in frame["road_states"]))
        self.assertEqual(frame["building_states"][0]["risk_level"], "high")
        self.assertIsNone(path(data["roads"], frame))
        data["scenario"]["params"]["road_status"]["SIM-R09"] = "blocked"
        with self.assertRaises(ValueError):
            simulate(**data)
