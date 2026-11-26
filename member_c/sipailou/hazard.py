"""CITYRESCUE deterministic scenario adapter. Python 3.9+; standard library."""
import argparse
import json
from pathlib import Path


def number(value, name, minimum=0, maximum=1_000_000):
    if type(value) not in (int, float) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be numeric in [{minimum}, {maximum}]")
    return value


def asset_ids(rows, key):
    ids = [row[key] for row in rows]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"Empty or duplicate {key}")
    return sorted(ids)


def mapping(params, key, ids):
    result = params.get(key, {})
    if not isinstance(result, dict) or set(result) - set(ids):
        raise ValueError(f"{key}: invalid map or unknown asset")
    return result


def simulate(scenario, roads, buildings):
    p = scenario["params"]
    if not isinstance(p, dict):
        raise ValueError("params must be an object")
    for key in ("scenario_id", "campus_id"):
        if not isinstance(scenario[key], str) or not scenario[key].strip():
            raise ValueError(key)
    for key in ("step_min", "duration_min", "seed"):
        if type(scenario[key]) is not int or (key != "seed" and scenario[key] < 1):
            raise ValueError(key)
    end, step = scenario["duration_min"], scenario["step_min"]
    road_ids = asset_ids(roads, "road_id")
    building_ids = asset_ids(buildings, "building_id")
    hazard = scenario["hazard_type"]
    manual = mapping(p, "manual_closed_from_min", road_ids)
    if any(type(t) is not int or t < 0 for t in manual.values()):
        raise ValueError("manual_closed_from_min")
    common = {"manual_closed_from_min"}
    if hazard == "flood":
        allowed = {"rainfall_mm_h", "closure_depth_m", "caution_depth_m", "drain_mm_h",
                   "catchment_factor", "building_road"}
        rain = number(p["rainfall_mm_h"], "rainfall_mm_h")
        drain = number(p.get("drain_mm_h", 10), "drain_mm_h")
        closed = number(p.get("closure_depth_m", .30), "closure_depth_m")
        caution = number(p.get("caution_depth_m", closed / 3), "caution_depth_m")
        if not 0 < caution < closed:
            raise ValueError("Require 0 < caution_depth_m < closure_depth_m")
        factors = mapping(p, "catchment_factor", road_ids)
        for factor in factors.values():
            number(factor, "catchment_factor", maximum=100)
        links = mapping(p, "building_road", building_ids)
        if any(i not in road_ids for i in links.values()):
            raise ValueError("building_road contains unknown road")
    elif hazard == "earthquake":
        allowed = {"road_status", "building_risk"}
        affected = mapping(p, "road_status", road_ids)
        risks = mapping(p, "building_risk", building_ids)
        if any(v not in ("open", "caution", "closed") for v in affected.values()):
            raise ValueError("road_status")
        if any(v not in ("low", "medium", "high", "unknown") for v in risks.values()):
            raise ValueError("building_risk")
    else:
        raise ValueError("hazard_type")
    if set(p) - common - allowed:
        raise ValueError("Unknown scenario parameter")
    frames = []
    for version, t in enumerate(range(0, end + step, step)):
        t = min(t, end)
        road_states, building_states, water_risk = [], [], {}
        for i in road_ids:
            if hazard == "flood":
                depth = round(max(0, rain * factors.get(i, 1) - drain) * t / 60000, 6)
                status = "closed" if depth >= closed else "caution" if depth >= caution else "open"
                water_risk[i] = {"closed": "high", "caution": "medium", "open": "low"}[status]
                reason = f"积水 {depth:g} m，警戒/禁行阈值 {caution:g}/{closed:g} m"
            else:
                depth = None
                status = affected.get(i, "open")
                reason = "固定地震影响区配置" if i in affected else "位于配置影响区外"
            source = "hazard"
            if i in manual and manual[i] <= t:
                status, source, reason = "closed", "manual", f"人工封路自第 {manual[i]} 分钟生效"
            road_states.append(dict(road_id=i, time_min=t, status=status, depth_m=depth,
                                    risk_penalty_min=3 if status == "caution" else 0,
                                    reason=reason, source=source, state_version=version))
        for i in building_ids:
            if hazard == "earthquake":
                risk, reason = risks.get(i, "unknown"), "固定影响区风险分级" if i in risks else "未配置建筑影响"
            else:
                risk = water_risk.get(links.get(i), "unknown")
                reason = f"邻接道路 {links[i]} 积水代理" if i in links else "无邻接道路映射"
            building_states.append(dict(building_id=i, time_min=t, risk_level=risk, reason=reason))
        frames.append(dict(time_min=t, state_version=version, road_states=road_states,
                           building_states=building_states))
    return frames


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    result = simulate(**payload)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
