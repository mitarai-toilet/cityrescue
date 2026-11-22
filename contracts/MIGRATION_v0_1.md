# v0.1 contract authority and migration

`contracts/schemas/*.schema.json` is the sole entity contract. The supplied Word
document describes these fields; the repository contract was frozen by captain instruction on 2026-11-22. The untracked Word document retains its historical review status.
`schema_v0_1.json` is now only an aggregate envelope referencing those schemas,
not a second set of entity definitions. `sample_v0_1.json` uses canonical fields
and synthetic fixture values. Historical definitions remain available in Git history.

| Historical format | Canonical format | Migration decision |
| --- | --- | --- |
| Road.from_node_id / to_node_id | from_node / to_node | Reference the same Node IDs |
| Road.geometry coordinate array | GeoJSON LineString object | Explicit geometry wrapper |
| Road.data_status | data_origin | No automatic mapping of verified to real; verification and origin differ |
| Road missing speed/direction | speed_kmh / one_way required | Supply independently verified values, or labelled synthetic fixture values |
| RoadState.risk_cost | risk_penalty_min | No conversion: historical units unknown |
| RoadState missing time/depth | time_min / depth_m required | Synthetic aggregate uses fixture values, not inferred historical measurements |
| Scenario.time_min / data_status / description | campus_id / params / duration_min / step_min | Reconstructed from synthetic scenario; no lossless automatic conversion |
| Vehicle.capacity / status | capability / available_at_min | No implied mapping; synthetic fixtures provide new values |
| Event.event_type | demand / status | No implied mapping; synthetic fixtures provide new values |
| DispatchResult.unassigned_event_ids | unassigned_events | Array of Event IDs |
| DispatchResult.explanation / data_status | ExplainResult plus Campus origin | Explanation is a separate entity, bound by run_id and state_version |
| DispatchResult missing run/version/outcome | run_id / state_version / outcome | New synthetic aggregate is a non-computed baseline |
| Assignment missing outcome | outcome, optional reason; nullable eta_min | ETA remains travel/arrival minutes, never risk penalty |

Common ID fields and length_m retain their names. Nonempty ID strings do not
imply referential integrity; cross-file tests and business validation are required.
No runtime consumers of the historical fields were found. The old field-dependent
test has been migrated to canonical aggregate validation.

Word limitations retained: RoadState.state_version/source are optional;
Scenario.params is an object without hazard-specific inner validation; Building
coordinates have no detailed polygon validation. Evidence IDs are nonempty strings,
not a schema-enforced registry. These are explicit contract limits, not implemented
simulation, dispatch or backend version-rejection guarantees.

Validation: `python -m pytest -q tests/test_contracts.py tests/test_fixture_integrity.py tests/test_schema_validation.py`.
ASGI health testing was attempted with a 20-second process deadline and timed out during execution. Repair is deferred. Contract freezing is separate from acceptance of the complete application.
