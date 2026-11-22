from pathlib import Path
from copy import deepcopy

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.campus import CampusDataError, DEFAULT_DATA, entity_schema, load_campus
from backend.simulation import FixtureSimulationProvider, RunStore, SimulationProvider
from backend.dispatching import DispatchProvider, FixtureDispatchProvider, validate_inputs, validate_result


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1, strict=True)
    params: dict | None = None


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state_version: int = Field(ge=0, strict=True)


class DispatchRequest(VersionRequest):
    run_id: str = Field(min_length=1, strict=True)
    vehicles: list[dict]
    events: list[dict]

def health() -> dict[str, str]:
    return {"status": "ok", "service": "cityrescue-api", "version": "0.1.0"}


def create_app(data_directory: Path = DEFAULT_DATA, simulation_provider: SimulationProvider | None = None,
               dispatch_provider: DispatchProvider | None = None) -> FastAPI:
    application = FastAPI(title="CITYRESCUE AI API", version="0.1.0",
                          description="v0.1 campus, synthetic replay and dispatch integration APIs. Default dispatch is fixture-only.")
    application.add_api_route("/health", health, methods=["GET"])

    @application.exception_handler(CampusDataError)
    async def data_error_handler(request: Request, exc: CampusDataError):
        return JSONResponse(status_code=503, content={"detail": {"code": exc.code, "message": str(exc)}})

    schemas = {name: entity_schema(name) for name in ("campus", "node", "road", "building")}
    graph_schema = {"type": "object", "required": ["campus", "nodes", "roads"], "properties": {
        "campus": schemas["campus"],
        "nodes": {"type": "array", "items": schemas["node"]},
        "roads": {"type": "array", "items": schemas["road"]}}, "additionalProperties": False}

    def register(path: str, key: str, schema: dict):
        async def query():
            data = load_campus(Path(data_directory))
            if key == "graph":
                return {field: data[field] for field in ("campus", "nodes", "roads")}
            return data[key]

        application.add_api_route(
            path, query, methods=["GET"], name=f"get_{key}", response_model=None,
            description="Synthetic campus fixture. Canonical entities; graph is an API wrapper. Data errors return 503.",
            responses={200: {"content": {"application/json": {"schema": schema}}},
                       503: {"description": "Missing, malformed or inconsistent source dataset"}},
        )

    register("/api/v1/campus", "campus", schemas["campus"])
    for name, plural in (("node", "nodes"), ("road", "roads"), ("building", "buildings")):
        register(f"/api/v1/campus/{plural}", plural, {"type": "array", "items": schemas[name]})
    register("/api/v1/campus/graph", "graph", graph_schema)

    store = RunStore(simulation_provider if simulation_provider is not None else FixtureSimulationProvider(Path(data_directory)))
    # One store per app/worker. No global current run or implicit GET mutations.
    application.state.simulation_runs = store

    def response(schema, status=200):
        return {status: {"content": {"application/json": {"schema": schema}}},
                404: {"description": "Scenario or run not found"},
                503: {"description": "Missing, malformed or inconsistent fixture"}}

    info_properties = {
        "run_id": {"type": "string"}, "scenario_id": {"type": "string"},
        "state_version": {"type": "integer", "minimum": 0},
        "time_min": {"type": "integer", "minimum": 0},
        "mode": {"const": "fixture_replay"}, "data_origin": {"const": "synthetic"},
        "scenario": entity_schema("scenario"),
        "provenance": {"type": "array", "items": {"type": "string"}},
    }
    info_schema = {"type": "object", "required": list(info_properties),
                   "properties": info_properties, "additionalProperties": False}
    state_properties = {**info_properties,
                        "roads": {"type": "array", "items": entity_schema("road_state")},
                        "buildings": {"type": "array", "items": entity_schema("building_state")}}
    state_schema = {"type": "object", "required": list(state_properties),
                    "properties": state_properties, "additionalProperties": False}

    @application.get("/api/v1/scenarios", responses=response({"type": "array", "items": entity_schema("scenario")}))
    async def scenarios():
        return store.provider.scenarios()

    @application.get("/api/v1/scenarios/{scenario_id}", responses=response(entity_schema("scenario")))
    async def scenario(scenario_id: str):
        return store.scenario(scenario_id)

    def info(snapshot):
        return {key: value for key, value in snapshot.items() if key not in ("roads", "buildings")}

    @application.post("/api/v1/simulation/runs", status_code=201, responses=response(info_schema, 201))
    async def create_run(body: CreateRun):
        return info(store.create(body.scenario_id, body.params))

    @application.get("/api/v1/simulation/runs/{run_id}", responses=response(info_schema))
    async def run(run_id: str):
        return info(store.get(run_id))

    @application.get("/api/v1/simulation/runs/{run_id}/roads", responses=response({"type": "array", "items": entity_schema("road_state")}))
    async def run_roads(run_id: str):
        return store.get(run_id)["roads"]

    @application.get("/api/v1/simulation/runs/{run_id}/buildings", responses=response({"type": "array", "items": entity_schema("building_state")}))
    async def run_buildings(run_id: str):
        return store.get(run_id)["buildings"]

    @application.get("/api/v1/simulation/runs/{run_id}/state", responses=response(state_schema))
    async def run_state(run_id: str):
        return store.get(run_id)

    @application.post('/api/v1/simulation/runs/{run_id}/roads/{road_id}/close')
    async def close_road(run_id: str, road_id: str, body: VersionRequest):
        return store.set_manual_closure(run_id, road_id, body.state_version, True)

    @application.post('/api/v1/simulation/runs/{run_id}/roads/{road_id}/open')
    async def open_road(run_id: str, road_id: str, body: VersionRequest):
        return store.set_manual_closure(run_id, road_id, body.state_version, False)

    @application.get('/api/v1/simulation/runs/{run_id}/history')
    async def run_history(run_id: str):
        return store.history(run_id)

    dispatcher = dispatch_provider if dispatch_provider is not None else FixtureDispatchProvider()
    dispatch_schema = {'type': 'object', 'required': ['provider', 'result'], 'properties': {
        'provider': {'type': 'string'}, 'result': entity_schema('dispatch_result')}, 'additionalProperties': False}

    @application.post('/api/v1/dispatch', responses=response(dispatch_schema))
    async def dispatch(body: DispatchRequest):
        snapshot = store.checked_snapshot(body.run_id, body.state_version)
        spatial = load_campus(Path(data_directory))
        validate_inputs(spatial, body.vehicles, body.events)
        result = dispatcher.dispatch(deepcopy(snapshot), deepcopy(spatial), deepcopy(body.vehicles), deepcopy(body.events))
        validate_result(result, snapshot, spatial, body.vehicles, body.events)
        wrapped = {'provider': dispatcher.name, 'result': result}
        store.record_dispatch(body.run_id, body.state_version, wrapped)
        return wrapped
    return application


app = create_app()
