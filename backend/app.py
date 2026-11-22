from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.campus import CampusDataError, DEFAULT_DATA, entity_schema, load_campus

def health() -> dict[str, str]:
    return {"status": "ok", "service": "cityrescue-api", "version": "0.1.0"}


def create_app(data_directory: Path = DEFAULT_DATA) -> FastAPI:
    application = FastAPI(title="CITYRESCUE AI API", version="0.1.0",
                          description="Read-only v0.1 campus API. Default data is synthetic, not a real campus survey.")
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
    return application


app = create_app()
