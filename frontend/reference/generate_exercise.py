"""Build a small OSM-derived exercise road graph for the existing dispatch backend."""

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import networkx as nx

from generate import tags_for


CAMPUS_ID = "OSM-JIULONGHU-EXERCISE"
WEST, SOUTH, EAST, NORTH = 118.8074, 31.8835, 118.8222, 31.8973
ROAD_TYPES = {"tertiary", "unclassified", "residential", "living_street", "service"}
BLOCKED_ACCESS = {"no", "private", "agricultural", "forestry"}


def distance(a, b):
    lon_a, lat_a, lon_b, lat_b = map(radians, (*a, *b))
    term = sin((lat_b - lat_a) / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin((lon_b - lon_a) / 2) ** 2
    return 12742000 * asin(sqrt(term))


def allowed(tags):
    if tags.get("highway") not in ROAD_TYPES or tags.get("area") == "yes":
        return False
    access = next((tags[key] for key in ("motorcar", "motor_vehicle", "vehicle", "access") if key in tags), "")
    return access not in BLOCKED_ACCESS


def road_graph(root):
    points = {node.attrib["id"]: [float(node.attrib["lon"]), float(node.attrib["lat"])] for node in root.findall("node")}
    in_area = {key for key, (lon, lat) in points.items() if WEST <= lon <= EAST and SOUTH <= lat <= NORTH}
    ways = []
    for way in root.findall("way"):
        tags = tags_for(way)
        if not allowed(tags):
            continue
        refs = [node.attrib["ref"] for node in way.findall("nd")]
        if len(refs) > 1 and all(ref in points for ref in refs):
            ways.append((way.attrib["id"], tags, refs))
    count = Counter(node for _, _, refs in ways for node in refs)
    roads = []
    graph = nx.DiGraph()
    for way_id, tags, refs in ways:
        start = None
        for index, node in enumerate(refs):
            if node not in in_area:
                start = None
                continue
            if start is None:
                start = index
                continue
            end_of_section = index + 1 == len(refs) or refs[index + 1] not in in_area or count[node] > 1
            if not end_of_section:
                continue
            section = refs[start:index + 1]
            start = index
            direction = tags.get("oneway", "yes" if tags.get("junction") == "roundabout" else "no")
            if direction == "-1":
                section.reverse()
            one_way = direction in {"yes", "1", "true", "-1"}
            first, last = section[0], section[-1]
            if first == last:
                continue
            geometry = [points[key] for key in section]
            length = sum(distance(a, b) for a, b in pairwise(geometry))
            if length < 1:
                continue
            road_id = f"JL-R{way_id}-{len(roads) + 1}"
            roads.append((road_id, first, last, geometry, round(length, 2), one_way))
            graph.add_edge(first, last, weight=length)
            if not one_way:
                graph.add_edge(last, first, weight=length)
    # Keep a mutually reachable graph so routine examples have valid alternatives.
    component = max(nx.strongly_connected_components(graph), key=len)
    return {key: points[key] for key in component}, [road for road in roads if road[1] in component and road[2] in component]


def feature(kind, coordinates, properties):
    return {"type": "Feature", "geometry": {"type": kind, "coordinates": coordinates}, "properties": properties}


def write(target, name, content):
    (target / name).write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def collection(features):
    return {"type": "FeatureCollection", "features": features}


def main():
    source, target = map(Path, sys.argv[1:])
    nodes, roads = road_graph(ET.parse(source).getroot())
    target.mkdir(parents=True, exist_ok=True)
    node_id = lambda key: f"JL-N{key}"
    write(target, "campus.json", {"campus_id": CAMPUS_ID, "name": "东南大学九龙湖校区",
        "coordinate_system": "WGS84", "data_origin": "estimated", "verified": False,
        "data_source": "OpenStreetMap 道路几何；课堂演练通行假设，未经实地核验"})
    write(target, "nodes.geojson", collection([
        feature("Point", point, {"node_id": node_id(key)}) for key, point in sorted(nodes.items())
    ]))
    write(target, "roads.geojson", collection([
        feature("LineString", shape, {"road_id": key, "from_node": node_id(first), "to_node": node_id(last),
            "length_m": length, "speed_kmh": 24, "one_way": one_way, "data_origin": "estimated"})
        for key, first, last, shape, length, one_way in roads
    ]))
    # Buildings on the reference layer are independent of this route calculation.
    write(target, "buildings.geojson", collection([]))
    write(target, "building_states.json", [])

    def nearest(coordinates):
        return node_id(min(nodes, key=lambda key: (distance(coordinates, nodes[key]), key)))

    vehicles = [{"vehicle_id": f"JL-V{index}", "node_id": nearest(point), "capability": ["general"], "available_at_min": 0}
                for index, point in enumerate(((118.8133, 31.8946), (118.8196, 31.8884)), 1)]
    events = [{"event_id": f"JL-E{index}", "node_id": nearest(point), "priority": index, "demand": 1, "status": "pending"}
              for index, point in enumerate(((118.8176, 31.8939), (118.8181, 31.8853), (118.8108, 31.8852)), 1)]
    write(target, "examples.json", {"vehicles": vehicles, "events": events})

    def nearest_road(point):
        return min(roads, key=lambda road: min(distance(point, p) for p in road[3]))[0]

    flood_closed = nearest_road((118.8099, 31.8941))
    caution = nearest_road((118.8122, 31.8937))
    quake_closed = nearest_road((118.8206, 31.8864))
    for hazard, params in (("flood", {"sample": "fixed-v1"}),
                           ("earthquake", {"affected_road_ids": [quake_closed]})):
        write(target, f"{hazard}_scenario.json", {"scenario_id": f"JL-{hazard.upper()}-01", "campus_id": CAMPUS_ID,
            "hazard_type": hazard, "params": params, "duration_min": 60, "step_min": 10, "seed": 42})
    states = []
    for time in (0, 20):
        for key, *_ in roads:
            status = "closed" if time and key == flood_closed else "caution" if time and key == caution else "open"
            depth = {"closed": 0.35, "caution": 0.12, "open": 0}
            states.append({"road_id": key, "time_min": time, "status": status, "depth_m": depth[status],
                "risk_penalty_min": 1 if status == "caution" else 0, "reason": "固定演练状态", "source": "hazard"})
    write(target, "road_states.json", states)
    print(f"{len(nodes)} nodes and {len(roads)} roads")


if __name__ == "__main__":
    main()
