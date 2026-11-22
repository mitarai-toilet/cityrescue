"""Fixed synthetic replay, not a disaster calculation engine."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from backend.campus import CampusDataError, entity_schema, load_campus, read_json


@dataclass
class Replay:
    scenario: dict
    time_min: int
    roads: list[dict]
    buildings: list[dict]
    provenance: list[str]


class SimulationProvider(Protocol):
    """Providers return canonical entities; run IDs and versions belong to the service."""

    def scenarios(self) -> list[dict]: ...

    def replay(self, scenario: dict) -> Replay: ...


def validate(entity: str, records: list[dict]):
    validator = Draft202012Validator(entity_schema(entity))
    for record in records:
        try:
            validator.validate(record)
        except ValidationError as exc:
            raise CampusDataError("invalid_simulation_data", f"Invalid {entity}: {exc.message}") from exc


class FixtureSimulationProvider:
    def __init__(self, directory: Path):
        self.directory = directory

    def scenarios(self):
        records = [read_json(self.directory / f"{hazard}_scenario.json") for hazard in ("flood", "earthquake")]
        validate("scenario", records)
        campus = load_campus(self.directory)["campus"]
        if len({s["scenario_id"] for s in records}) != len(records):
            raise CampusDataError("duplicate_id", "Duplicate scenario ID")
        for scenario in records:
            if scenario["campus_id"] != campus["campus_id"]:
                raise CampusDataError("invalid_reference", "Scenario references missing Campus")
        return deepcopy(records)

    def replay(self, scenario):
        spatial = load_campus(self.directory)
        states = read_json(self.directory / "road_states.json")
        if not isinstance(states, list):
            raise CampusDataError("invalid_simulation_data", "Road states must be an array")
        validate("road_state", states)
        ids = {r["road_id"] for r in spatial["roads"]}
        keys = [(s["time_min"], s["road_id"]) for s in states]
        if len(keys) != len(set(keys)) or any(s["road_id"] not in ids for s in states):
            raise CampusDataError("invalid_simulation_data", "Duplicate or unknown road state")
        if any(s["time_min"] > scenario["duration_min"] or s["time_min"] % scenario["step_min"] for s in states):
            raise CampusDataError("invalid_simulation_data", "Invalid fixture time slice")
        if scenario["hazard_type"] == "flood":
            roads = [deepcopy(s) for s in states if s["time_min"] == 20]
            buildings = []
            provenance = ["road_states.json at time_min=20; no flood building fixture"]
        else:
            params = scenario["params"]
            closed = params.get("affected_road_ids")
            if not isinstance(closed, list) or any(not isinstance(r, str) for r in closed) or not set(closed) <= ids:
                raise CampusDataError("invalid_simulation_data", "Invalid fixed earthquake road IDs")
            # Only apply explicit fixed closures; never reuse flood depth or risk values.
            roads = []
            for baseline in states:
                if baseline["time_min"] == 0:
                    rid = baseline["road_id"]
                    roads.append({"road_id": rid, "time_min": 20,
                                  "status": "closed" if rid in closed else "open", "depth_m": None,
                                  "risk_penalty_min": 0, "source": "hazard",
                                  "reason": "Synthetic fixed earthquake closure" if rid in closed else "Synthetic fixed baseline"})
            buildings = read_json(self.directory / "building_states.json")
            if not isinstance(buildings, list):
                raise CampusDataError("invalid_simulation_data", "Building states must be an array")
            provenance = ["road_states.json baseline IDs; earthquake_scenario.json explicit closures", "building_states.json"]
        if {s["road_id"] for s in roads} != ids or len(roads) != len(ids):
            raise CampusDataError("invalid_simulation_data", "Incomplete fixed road snapshot")
        building_ids = {b["building_id"] for b in spatial["buildings"]}
        validate("building_state", buildings)
        if (len({s["building_id"] for s in buildings}) != len(buildings)
                or any(s["building_id"] not in building_ids or s["time_min"] != 20 for s in buildings)):
            raise CampusDataError("invalid_simulation_data", "Invalid fixed building snapshot")
        return Replay(deepcopy(scenario), 20, roads, deepcopy(buildings), provenance)


class RunStore:
    """App-local memory. Atomic publication and defensive copies isolate all readers."""

    def __init__(self, provider: SimulationProvider):
        self.provider = provider
        self._runs = {}
        self._lock = Lock()

    def scenario(self, scenario_id):
        for scenario in self.provider.scenarios():
            if scenario["scenario_id"] == scenario_id:
                return scenario
        raise HTTPException(404, detail={"code": "scenario_not_found"})

    def create(self, scenario_id, params=None):
        scenario = self.scenario(scenario_id)
        if params is not None and params != scenario["params"]:
            raise HTTPException(422, detail={"code": "unsupported_replay_parameters", "message": "Only exact fixture params are supported"})
        replay = self.provider.replay(scenario)
        validate("scenario", [replay.scenario])
        validate("road_state", replay.roads)
        validate("building_state", replay.buildings)
        if replay.scenario != scenario or not isinstance(replay.time_min, int) or replay.time_min < 0:
            raise CampusDataError("invalid_simulation_data", "Provider returned a different scenario or invalid time")
        for kind, records in (("road", replay.roads), ("building", replay.buildings)):
            if (len({record[f"{kind}_id"] for record in records}) != len(records)
                    or any(record["time_min"] != replay.time_min for record in records)):
                raise CampusDataError("invalid_simulation_data", "Provider snapshot is inconsistent")
        # This is the only publication point. Future updates must publish a complete
        # validated snapshot under this lock; GET handlers never update this mapping.
        with self._lock:
            run_id = "run-" + uuid4().hex
            while run_id in self._runs:
                run_id = "run-" + uuid4().hex
            roads = [{**s, "state_version": 0} for s in replay.roads]
            snapshot = {"run_id": run_id, "scenario_id": scenario_id, "state_version": 0,
                        "time_min": replay.time_min, "mode": "fixture_replay", "data_origin": "synthetic",
                        "scenario": deepcopy(replay.scenario), "provenance": replay.provenance,
                        "roads": roads, "buildings": deepcopy(replay.buildings)}
            self._runs[run_id] = deepcopy(snapshot)
            return deepcopy(snapshot)

    def get(self, run_id):
        with self._lock:
            if run_id not in self._runs:
                raise HTTPException(404, detail={"code": "run_not_found"})
            return deepcopy(self._runs[run_id])
