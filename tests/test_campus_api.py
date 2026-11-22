"""Real local Uvicorn HTTP checks, with bounded startup and request deadlines."""

import json
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import pytest
from jsonschema import Draft202012Validator

from backend.campus import DEFAULT_DATA, ROOT, CampusDataError, load_campus


@contextmanager
def server(directory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    code = (
        "import sys,uvicorn; from pathlib import Path; from backend.app import create_app; "
        "uvicorn.run(create_app(Path(sys.argv[1])),host='127.0.0.1',port=int(sys.argv[2]),log_level='error')"
    )
    proc = subprocess.Popen([sys.executable, "-u", "-c", code, str(directory), str(port)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    opener = build_opener(ProxyHandler({}))
    url = f"http://127.0.0.1:{port}"

    def request(path, body=None):
        target = url + path
        if body is not None:
            target = Request(target, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"}, method="POST")
        try:
            with opener.open(target, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    try:
        deadline = time.monotonic() + 10
        while True:
            if proc.poll() is not None:
                raise AssertionError(proc.stdout.read().decode(errors="replace"))
            try:
                status, _ = request("/openapi.json")
                if status == 200:
                    break
            except (OSError, URLError):
                pass
            if time.monotonic() > deadline:
                raise AssertionError("Uvicorn did not become ready within 10 seconds")
            time.sleep(0.05)
        yield request
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=4)


def test_campus_http_endpoints_and_health():
    with server(DEFAULT_DATA) as request:
        assert request("/health") == (200, {"status": "ok", "service": "cityrescue-api", "version": "0.1.0"})
        status, openapi = request("/openapi.json")
        assert status == 200
        expected = load_campus()
        for suffix, key in (("", "campus"), ("/nodes", "nodes"), ("/roads", "roads"),
                            ("/buildings", "buildings"), ("/graph", "graph")):
            path = "/api/v1/campus" + suffix
            status, body = request(path)
            assert status == 200
            schema = openapi["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(body)
            assert body == ({k: expected[k] for k in ("campus", "nodes", "roads")} if key == "graph" else expected[key])
        assert expected["campus"]["data_origin"] == "synthetic"
        assert expected["campus"]["verified"] is False
        assert len(expected["nodes"]) == 9 and len(expected["roads"]) == 16 and len(expected["buildings"]) == 5


@pytest.mark.parametrize("corruption,code", [
    ("missing", "data_file_missing"), ("json", "invalid_json"),
    ("reference", "invalid_reference"), ("duplicate", "duplicate_id"),
    ("schema", "invalid_entity"), ("geojson", "invalid_geojson"),
])
def test_data_errors_return_explicit_http_503(tmp_path, corruption, code):
    directory = tmp_path / "campus"
    shutil.copytree(DEFAULT_DATA, directory)
    path = directory / "roads.geojson"
    if corruption == "missing":
        path.unlink()
    elif corruption == "json":
        path.write_text("{broken", encoding="utf-8")
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        if corruption == "reference":
            data["features"][0]["properties"]["from_node"] = "NONEXISTENT"
        elif corruption == "duplicate":
            data["features"].append(data["features"][0])
        elif corruption == "schema":
            data["features"][0]["properties"]["speed_kmh"] = -1
        else:
            data["type"] = "NotFeatureCollection"
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CampusDataError) as exc:
        load_campus(directory)
    assert exc.value.code == code
    with server(directory) as request:
        status, body = request("/api/v1/campus/roads")
        assert status == 503 and body["detail"]["code"] == code
        assert request("/health")[0] == 200
