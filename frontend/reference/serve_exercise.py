"""Run the D dispatch backend against the geographically aligned exercise dataset."""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True, help="Path to the D backend worktree")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    backend_root = args.backend.resolve()
    if not (backend_root / "backend" / "networkx_dispatch.py").is_file():
        parser.error("Select the worktree containing D's NetworkX provider")
    sys.path.insert(0, str(backend_root))

    import uvicorn
    from backend.app import create_app
    from backend.networkx_dispatch import NetworkXDispatchProvider

    dataset = Path(__file__).resolve().parent / "exercise-data"
    examples = json.loads((dataset / "examples.json").read_text(encoding="utf-8"))
    app = create_app(data_directory=dataset, dispatch_provider=NetworkXDispatchProvider())

    @app.get("/api/v1/exercise/examples")
    def get_examples():
        return examples

    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
