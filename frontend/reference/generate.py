"""Build the offline campus reference from a bounded OpenStreetMap XML export."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROAD_CLASSES = {
    "primary", "secondary", "tertiary", "unclassified", "residential",
    "living_street", "service", "pedestrian", "footway", "cycleway", "path",
}
MAIN_ROADS = {"primary", "secondary", "tertiary"}
LANDMARK_NAMES = {
    "九龙湖", "李文正图书馆", "图书馆", "焦廷标馆", "梅园食堂",
    "桃园食堂", "橘园食堂", "体育馆", "大学生活动中心",
    "体育中心", "东南大学九龙湖校区南门", "东南大学九龙湖校区东门",
    "东南大学九龙湖校区北门", "东南大学九龙湖校区西门",
}


def classify(tags, closed):
    if closed:
        if "building" in tags:
            return "building"
        if tags.get("natural") == "water" or tags.get("landuse") in {"reservoir", "basin"}:
            return "water"
        if tags.get("amenity") == "university":
            return "campus"
        if tags.get("leisure") in {"pitch", "track", "playground", "stadium"}:
            return "sport"
        if tags.get("landuse") in {"grass", "forest", "meadow"} or tags.get("leisure") in {"park", "garden"}:
            return "green"
    highway = tags.get("highway")
    if highway in ROAD_CLASSES:
        if highway in MAIN_ROADS:
            return "main-road"
        return "walk" if highway in {"footway", "path", "pedestrian", "cycleway"} else "road"
    return None


def tags_for(element):
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def add_landmark(landmarks, name, position):
    if name in LANDMARK_NAMES and name not in landmarks:
        landmarks[name] = position


def main():
    source, destination = map(Path, sys.argv[1:])
    root = ET.parse(source).getroot()
    nodes = {}
    landmarks = {}
    for node in root.findall("node"):
        position = [round(float(node.attrib["lon"]), 7), round(float(node.attrib["lat"]), 7)]
        nodes[node.attrib["id"]] = position
        add_landmark(landmarks, tags_for(node).get("name"), position)

    features = []
    for way in root.findall("way"):
        ids = [node.attrib["ref"] for node in way.findall("nd")]
        if len(ids) < 2 or any(node_id not in nodes for node_id in ids):
            continue
        points = [nodes[node_id] for node_id in ids]
        closed = len(ids) >= 4 and ids[0] == ids[-1]
        tags = tags_for(way)
        kind = classify(tags, closed)
        if not kind:
            continue
        is_area = kind in {"building", "water", "campus", "sport", "green"}
        geometry = {"type": "Polygon", "coordinates": [points]} if is_area else {
            "type": "LineString", "coordinates": points,
        }
        feature = {
            "type": "Feature", "id": int(way.attrib["id"]),
            "properties": {"kind": kind}, "geometry": geometry,
        }
        features.append(feature)
        if is_area and tags.get("name") in LANDMARK_NAMES:
            center = [round((min(axis) + max(axis)) / 2, 7) for axis in zip(*points)]
            add_landmark(landmarks, tags["name"], center)

    payload = {
        "type": "FeatureCollection", "features": features,
        "landmarks": [{"name": name, "position": point} for name, point in landmarks.items()],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(features)} features, {len(landmarks)} named landmarks")


if __name__ == "__main__":
    main()
