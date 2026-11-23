"""Calculated campus states for the synchronous C/E integration interface."""
from copy import deepcopy
from pathlib import Path

from backend.campus import DEFAULT_DATA, load_campus
from backend.providers import ProviderError
from backend.simulation import FixtureSimulationProvider, Replay
from member_c.hazard import simulate


class CProvider:
    def __init__(self, directory: Path = DEFAULT_DATA):
        self.directory = Path(directory)

    def scenarios(self):
        return FixtureSimulationProvider(self.directory).scenarios()

    def replay(self, scenario):
        spatial = load_campus(self.directory)
        model_input = deepcopy(scenario)
        params = model_input["params"]
        if model_input["hazard_type"] == "earthquake":
            # The frozen campus fixture identifies affected roads explicitly.
            # A risk seed alone gives no evidence of structural damage.
            params.pop("building_risk_seed", None)
            if "affected_road_ids" in params:
                ids = params.pop("affected_road_ids")
                if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                    raise ProviderError("invalid_affected_roads", 400)
                params["road_status"] = {**params.get("road_status", {}), **dict.fromkeys(ids, "closed")}
        try:
            frames = simulate(model_input, spatial["roads"], spatial["buildings"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ProviderError("invalid_model_parameters", 400) from exc
        # E publishes one step-aligned snapshot and assigns the run's version.
        frame = next(f for f in reversed(frames) if f["time_min"] % scenario["step_min"] == 0)
        roads = [{k: v for k, v in row.items() if k != "state_version"} for row in frame["road_states"]]
        return Replay(deepcopy(scenario), frame["time_min"], roads, frame["building_states"],
                      ["按情景参数计算；输出为教学推演，水深与建筑风险未经实测校准。"],
                      mode="simulation", data_origin="synthetic")
