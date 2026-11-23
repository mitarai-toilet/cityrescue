import unittest
from test_hazard import read
from simulation_provider import SimulationProvider


class CampusIntegration(unittest.TestCase):
    def test_campus_snapshots_and_detour(self):
        nodes = {n["node_id"]: n["position"]["coordinates"] for n in read("nodes.json")}
        for hazard in ("flood", "earthquake"):
            payload = read(f"jlh_{hazard}.input.json")
            frames = SimulationProvider().simulate(**payload)
            self.assertEqual(frames, read(f"jlh_{hazard}.output.json"))
            self.assertEqual(len(frames), 7)
            roads = {r["road_id"]: r for r in payload["roads"]}
            for r in roads.values():
                self.assertEqual(r["geometry"]["coordinates"], [nodes[r["from_node"]], nodes[r["to_node"]]])
            states = {s["road_id"]: s for s in frames[5]["road_states"]}
            self.assertEqual(states["JLH-R2"]["status"], "closed")
            node = "JLH-N1"
            for rid in ["JLH-R1", "JLH-R6", "JLH-R4", "JLH-R7"]:
                road = roads[rid]
                self.assertNotEqual(states[rid]["status"], "closed")
                a, b = road["from_node"], road["to_node"]
                self.assertIn(node, (a, b))
                node = b if node == a else a
            self.assertEqual(node, "JLH-N3")
