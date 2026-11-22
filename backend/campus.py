"""Read-only canonical campus entities, loaded from repository fixtures."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError, SchemaError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "fixtures" / "synthetic_campus"
SCHEMAS = ROOT / "contracts" / "schemas"


class CampusDataError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise CampusDataError("data_file_missing", f"Required file missing: {path.name}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CampusDataError("invalid_json", f"Invalid JSON: {path.name}") from exc
    except OSError as exc:
        raise CampusDataError("data_read_error", f"Cannot read: {path.name}") from exc


def entity_schema(entity: str) -> dict:
    schema = read_json(SCHEMAS / f"{entity}.schema.json")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CampusDataError("invalid_schema", f"Invalid schema: {entity}") from exc
    return schema


def load_campus(directory: Path = DEFAULT_DATA) -> dict:
    """Validate the full spatial dataset before returning any of its entities.

    GeoJSON is a storage wrapper. API Node.position and Road/Building.geometry
    are reconstructed as canonical entities without mutating source files.
    """
    campus = read_json(directory / "campus.json")
    result = {"campus": campus}
    for entity, collection in (("node", "nodes"), ("road", "roads"), ("building", "buildings")):
        document = read_json(directory / f"{collection}.geojson")
        try:
            if document["type"] != "FeatureCollection" or not isinstance(document["features"], list):
                raise ValueError("Expected FeatureCollection")
            records = []
            for feature in document["features"]:
                if feature["type"] != "Feature" or not isinstance(feature["properties"], dict):
                    raise ValueError("Expected Feature with object properties")
                records.append({**feature["properties"],
                                "position" if entity == "node" else "geometry": feature["geometry"]})
            result[collection] = records
        except (KeyError, TypeError, ValueError) as exc:
            raise CampusDataError("invalid_geojson", f"Invalid FeatureCollection: {collection}") from exc
    for entity, records in (("campus", [campus]), ("node", result["nodes"]),
                            ("road", result["roads"]), ("building", result["buildings"])):
        validator = Draft202012Validator(entity_schema(entity))
        try:
            for record in records:
                validator.validate(record)
        except ValidationError as exc:
            raise CampusDataError("invalid_entity", f"Invalid {entity} field: {'.'.join(map(str, exc.absolute_path))}") from exc
        ids = [record[f"{entity}_id"] for record in records]
        if len(ids) != len(set(ids)):
            raise CampusDataError("duplicate_id", f"Duplicate {entity} ID")
    nodes = {node["node_id"]: node for node in result["nodes"]}
    for road in result["roads"]:
        if road["from_node"] not in nodes or road["to_node"] not in nodes:
            raise CampusDataError("invalid_reference", f"Road {road['road_id']} references missing Node")
        if (road["geometry"]["coordinates"][0] != nodes[road["from_node"]]["position"]["coordinates"]
                or road["geometry"]["coordinates"][-1] != nodes[road["to_node"]]["position"]["coordinates"]):
            raise CampusDataError("invalid_reference", f"Road {road['road_id']} geometry endpoints differ from Nodes")
    return result
