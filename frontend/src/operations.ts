import type { Assignment, Dispatch, RescueEvent, Vehicle } from './api';

export interface TaskResult {
  version: number;
  assignment?: Assignment;
  startNode?: string;
  previous?: Pick<TaskResult, 'version' | 'startNode'> & { assignment: Assignment };
  noVehicles?: boolean;
}

export interface Board {
  events: RescueEvent[];
  vehicles: Vehicle[];
  results: Record<string, TaskResult>;
}

export const newBoard = (vehicles: Vehicle[] = []): Board => ({ events: [], vehicles, results: {} });

const storageKey = 'cityrescue-b-jiulonghu-v1';
export function readDraft(): { runId: string; board: Board } | null {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    const draft = JSON.parse(raw);
    if (typeof draft.runId === 'string' && Array.isArray(draft.board?.events) &&
      Array.isArray(draft.board.vehicles) && draft.board.results) return draft;
  } catch { /* The workspace still works when storage is unavailable. */ }
  return null;
}

export function writeDraft(runId: string | null, board: Board) {
  try {
    if (runId) sessionStorage.setItem(storageKey, JSON.stringify({ runId, board }));
    else sessionStorage.removeItem(storageKey);
  } catch { /* Persistence is limited to this browser tab. */ }
}

export function reserveVehicles(board: Board, time: number, allUnavailable: boolean): Vehicle[] {
  const occupied = new Set(board.events.flatMap((event) => {
    if (event.status !== 'assigned' && event.status !== 'in_progress') return [];
    const vehicle = board.results[event.event_id]?.assignment?.vehicle_id;
    return vehicle ? [vehicle] : [];
  }));
  return board.vehicles.map((vehicle) => allUnavailable || occupied.has(vehicle.vehicle_id)
    ? { ...vehicle, available_at_min: Math.max(vehicle.available_at_min, time + 1) } : vehicle);
}

export function applyDispatch(board: Board, response: Dispatch, vehicles: Vehicle[], noVehicles = false): Board {
  const { assignments, unassigned_events, state_version: version } = response.result;
  const results = { ...board.results };
  for (const assignment of assignments) {
    const old = results[assignment.event_id];
    const previous = old?.version === version ? old.previous : old?.assignment && {
      assignment: old.assignment, version: old.version, startNode: old.startNode,
    };
    results[assignment.event_id] = {
      version, assignment, previous,
      startNode: vehicles.find((vehicle) => vehicle.vehicle_id === assignment.vehicle_id)?.node_id,
    };
  }
  for (const id of unassigned_events) results[id] = { version, noVehicles };
  const assigned = new Set(assignments.filter((assignment) => assignment.outcome === 'assigned')
    .map((assignment) => assignment.event_id));
  const events = board.events.map((event): RescueEvent =>
    event.status === 'pending' && assigned.has(event.event_id) ? { ...event, status: 'assigned' } : event);
  return { ...board, events, results };
}
