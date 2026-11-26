import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type { Assignment, Graph, RescueEvent, Snapshot, Vehicle } from './api';

export const roadColors = { open: '#527f7b', caution: '#b76a18', closed: '#b54045', unknown: '#78888b' };

export interface ExerciseLayers {
  graph: Graph;
  run: Snapshot;
  vehicles: Vehicle[];
  events: RescueEvent[];
  current: Assignment[];
  previous: Assignment[];
  focusedTaskId: string | null;
  focusedVehicleId?: string;
  roadId: string;
  nodeId: string;
  onRoad: (id: string) => void;
  onNode: (id: string) => void;
  onTask: (id: string) => void;
}

const feature = (geometry: Geometry, properties: Record<string, unknown> = {}): Feature =>
  ({ type: 'Feature', geometry, properties });
const collection = (features: Feature[] = []): FeatureCollection =>
  ({ type: 'FeatureCollection', features });

const sourceIds = ['roads', 'nodes', 'events', 'vehicles', 'previous', 'current'];

export function addExerciseLayers(map: MapLibreMap, current: () => ExerciseLayers | null) {
  for (const id of sourceIds) {
    map.addSource(id, { type: 'geojson', data: collection() });
  }

  map.addLayer({ id: 'roads', type: 'line', source: 'roads',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-width': ['case', ['get', 'selected'], 6, ['==', ['get', 'status'], 'open'], 2, 4],
      'line-opacity': ['case', ['get', 'selected'], 1, ['==', ['get', 'status'], 'open'], .56, 1],
      'line-color': ['match', ['get', 'status'], 'open', roadColors.open, 'caution',
        roadColors.caution, 'closed', roadColors.closed, roadColors.unknown],
    } });
  map.addLayer({ id: 'closed-road-pattern', type: 'line', source: 'roads',
    filter: ['==', ['get', 'status'], 'closed'],
    paint: { 'line-color': '#fff4ec', 'line-width': 1.5, 'line-dasharray': [2, 3] } });
  map.addLayer({ id: 'previous', type: 'line', source: 'previous',
    paint: { 'line-color': '#3b484e', 'line-width': 3, 'line-dasharray': [2, 2],
      'line-opacity': ['case', ['get', 'emphasized'], 1, .34] },
    layout: { 'line-cap': 'round' } });
  map.addLayer({ id: 'current-outline', type: 'line', source: 'current',
    paint: { 'line-color': '#f7fcfb', 'line-width': ['case', ['get', 'emphasized'], 10, 5] },
    layout: { 'line-cap': 'round', 'line-join': 'round' } });
  map.addLayer({ id: 'current', type: 'line', source: 'current',
    paint: { 'line-color': '#156fb4', 'line-width': ['case', ['get', 'emphasized'], 6, 3],
      'line-opacity': ['case', ['get', 'emphasized'], 1, .4] },
    layout: { 'line-cap': 'round', 'line-join': 'round' } });
  map.addLayer({ id: 'nodes', type: 'circle', source: 'nodes',
    paint: { 'circle-color': '#f8fcfa', 'circle-stroke-color': '#476765',
      'circle-stroke-width': ['case', ['get', 'selected'], 3, 1.5],
      'circle-radius': ['case', ['get', 'selected'], 6, 2.2] } });
  map.addLayer({ id: 'vehicles', type: 'circle', source: 'vehicles',
    paint: { 'circle-color': '#156fb4', 'circle-radius': ['case', ['get', 'selected'], 9, 6], 'circle-stroke-color': '#fff',
      'circle-opacity': ['case', ['get', 'emphasized'], 1, .45],
      'circle-stroke-width': 2, 'circle-translate': [-7, -9] } });
  map.addLayer({ id: 'events', type: 'circle', source: 'events',
    paint: { 'circle-color': '#923c70', 'circle-radius': ['case', ['get', 'selected'], 9, 6], 'circle-stroke-color': '#fff',
      'circle-opacity': ['case', ['get', 'emphasized'], 1, .45],
      'circle-stroke-width': 2, 'circle-translate': [7, -9] } });

  map.on('click', ({ point }) => {
    const handlers = current();
    if (!handlers) return;
    const box: [[number, number], [number, number]] = [
      [point.x - 4, point.y - 4], [point.x + 4, point.y + 4],
    ];
    const hits = map.queryRenderedFeatures(box, { layers: ['nodes', 'roads', 'events'] });
    const task = hits.find((item) => item.layer.id === 'events');
    const node = hits.find((item) => item.layer.id === 'nodes');
    const road = hits.find((item) => item.layer.id === 'roads');
    if (task) handlers.onTask(String(task.properties.id));
    else if (node) handlers.onNode(String(node.properties.id));
    else if (road) handlers.onRoad(String(road.properties.id));
  });
  for (const layer of ['roads', 'nodes', 'events']) {
    map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
  }
}

export function renderExercise(map: MapLibreMap, props: ExerciseLayers | null) {
  if (!props) {
    for (const id of sourceIds) map.getSource<GeoJSONSource>(id)?.setData(collection());
    return;
  }
  const nodes = new Map(props.graph.nodes.map((node) => [node.node_id, node.position]));
  const roads = new Map(props.graph.roads.map((road) => [road.road_id, road.geometry]));
  const status = new Map(props.run?.roads.map((road) => [road.road_id, road.status]));
  const point = (id: string, nodeId: string, focusedId: string | null | undefined) => {
    const geometry = nodes.get(nodeId);
    return geometry ? [feature(geometry, { id, selected: id === focusedId, emphasized: !props.focusedTaskId || id === focusedId })] : [];
  };
  const lines = (assignments: Assignment[]) => assignments.flatMap((assignment) =>
    assignment.road_ids.flatMap((id) => {
      const geometry = roads.get(id);
      return geometry ? [feature(geometry, {
        emphasized: !props.focusedTaskId || assignment.event_id === props.focusedTaskId,
      })] : [];
    }));
  const sources = {
    roads: props.graph.roads.map((road) => feature(road.geometry, {
      id: road.road_id, status: status.get(road.road_id) ?? 'unknown', selected: road.road_id === props.roadId,
    })),
    nodes: props.graph.nodes.map((node) => feature(node.position, {
      id: node.node_id, selected: node.node_id === props.nodeId,
    })),
    events: props.events.flatMap((event) => point(event.event_id, event.node_id, props.focusedTaskId)),
    vehicles: props.vehicles.flatMap((vehicle) => point(vehicle.vehicle_id, vehicle.node_id, props.focusedVehicleId)),
    previous: lines(props.previous),
    current: lines(props.current),
  };
  for (const [id, features] of Object.entries(sources)) {
    map.getSource<GeoJSONSource>(id)?.setData(collection(features));
  }
}
