import type { LineString, MultiPolygon, Point, Polygon } from 'geojson';

export type Origin = 'synthetic' | 'estimated' | 'real';
export type RoadStatus = 'open' | 'caution' | 'closed';

export interface Node {
  node_id: string;
  position: Point;
}
export interface Road {
  road_id: string;
  from_node: string;
  to_node: string;
  one_way: boolean;
  geometry: LineString;
}
export interface Building {
  building_id: string;
  geometry: Polygon | MultiPolygon;
}
export interface Graph {
  campus: { name: string; data_origin: Origin; verified: boolean };
  nodes: Node[];
  roads: Road[];
}
export interface Scenario {
  scenario_id: string;
  hazard_type: 'flood' | 'earthquake';
}
export interface Snapshot {
  run_id: string;
  scenario_id: string;
  state_version: number;
  time_min: number;
  data_origin: Origin;
  mode: 'fixture_replay' | 'simulation';
  roads: { road_id: string; status: RoadStatus; source: string; depth_m: number | null }[];
}
export interface Vehicle {
  vehicle_id: string;
  node_id: string;
  capability: string[];
  available_at_min: number;
}
export interface ExerciseExamples {
  vehicles: Vehicle[];
  events: RescueEvent[];
}
export interface RescueEvent {
  event_id: string;
  node_id: string;
  priority: number;
  demand: number;
  status: 'pending' | 'in_progress' | 'assigned' | 'completed';
}
export interface Assignment {
  event_id: string;
  vehicle_id: string;
  road_ids: string[];
  eta_min: number | null;
  outcome: 'assigned' | 'unreachable';
  reason?: string | null;
}
export interface Dispatch {
  provider: string;
  result: {
    run_id: string;
    state_version: number;
    assignments: Assignment[];
    unassigned_events: string[];
  };
}
interface History {
  dispatches: Dispatch[];
  changes: { road_id: string; action: 'close' | 'open'; state_version: number }[];
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`HTTP ${status}`);
  }
}

async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch('/api/v1' + path, {
    signal: AbortSignal.timeout(10000),
    ...(body && {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, payload?.detail);
  if (payload === null) throw new ApiError(502, { code: 'invalid_response' });
  return payload as T;
}

const runPath = (id: string) => '/simulation/runs/' + encodeURIComponent(id);
export const api = {
  graph: () => request<Graph>('/campus/graph'),
  examples: () => request<ExerciseExamples>('/exercise/examples'),
  scenarios: () => request<Scenario[]>('/scenarios'),
  start: (scenario_id: string) => request<{ run_id: string }>('/simulation/runs', { scenario_id }),
  state: (id: string) => request<Snapshot>(runPath(id) + '/state'),
  history: (id: string) => request<History>(runPath(id) + '/history'),
  changeRoad: (run: Snapshot, road: string, close: boolean) =>
    request<{ state_version: number }>(
      runPath(run.run_id) + '/roads/' + encodeURIComponent(road) + (close ? '/close' : '/open'),
      { state_version: run.state_version },
    ),
  dispatch: (run: Snapshot, vehicles: Vehicle[], events: RescueEvent[], index?: number) =>
    request<Dispatch>(index === undefined ? '/dispatch' : '/dispatch/replan', {
      run_id: run.run_id, state_version: run.state_version, vehicles, events,
      ...(index === undefined ? {} : { previous_dispatch_index: index }),
    }),
};
