from pathlib import Path

import pytest

from backend.app import create_app
from backend.campus import DEFAULT_DATA
from backend.c_hazard import CProvider


@pytest.mark.parametrize("directory", [DEFAULT_DATA, Path(__file__).resolve().parents[1] / "member_c" / "jlh_campus"])
def test_publish_both_hazards(directory):
    provider = CProvider(directory)
    store = create_app(data_directory=directory, simulation_provider=provider).state.simulation_runs
    scenarios = store.scenarios()
    assert {s["hazard_type"] for s in scenarios} == {"flood", "earthquake"}
    for scenario in scenarios:
        replay = provider.replay(scenario)
        assert replay == provider.replay(scenario)
        assert replay.buildings and replay.mode == "simulation"
        assert store.create(scenario["scenario_id"])["state_version"] == 0
        if scenario["hazard_type"] == "earthquake":
            assert any(r["status"] == "closed" for r in replay.roads)
