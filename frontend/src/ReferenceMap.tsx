import { useEffect, useRef, useState } from 'react';
import { LngLatBounds, Map as MapLibreMap, Marker, NavigationControl, ScaleControl, setWorkerUrl, type FilterSpecification } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import type { FeatureCollection, Position } from 'geojson';
import { addExerciseLayers, renderExercise, type ExerciseLayers } from './exerciseLayers';

setWorkerUrl(workerUrl);

interface ReferenceData extends FeatureCollection {
  landmarks: { name: string; position: Position }[];
}

const mapBounds = new LngLatBounds([118.789, 31.868], [118.842, 31.914]);
const campusBounds = new LngLatBounds([118.8068, 31.8827], [118.8227, 31.8982]);
const mapUrl = 'https://www.openstreetmap.org/way/171389014';
const kinds = (...values: string[]): FilterSpecification =>
  ['match', ['get', 'kind'], values, true, false];

function addReferenceLayers(map: MapLibreMap, data: ReferenceData) {
  map.addSource('local-campus', { type: 'geojson', data, attribution: '© OpenStreetMap contributors' });
  const areas = [
    ['campus', '#e8efdf', '#a3b5a1'],
    ['green', '#cbdec3', '#b8cdb4'],
    ['sport', '#c2dcca', '#99b9a8'],
    ['water', '#a9ccdc', '#88b7ca'],
  ];
  for (const [kind, fill, outline] of areas) {
    map.addLayer({ id: kind, type: 'fill', source: 'local-campus', filter: kinds(kind),
      paint: { 'fill-color': fill, 'fill-outline-color': outline } });
  }
  map.addLayer({ id: 'street-borders', type: 'line', source: 'local-campus', filter: kinds('road', 'main-road'),
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#ccd3c9',
      'line-width': ['interpolate', ['linear'], ['zoom'], 14, 2.4, 18, 12] } });
  map.addLayer({ id: 'streets', type: 'line', source: 'local-campus', filter: kinds('road', 'main-road'),
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': ['match', ['get', 'kind'], 'main-road', '#fff7dd', '#fffefa'],
      'line-width': ['interpolate', ['linear'], ['zoom'], 14, 1.5, 18, 10] } });
  map.addLayer({ id: 'footpaths', type: 'line', source: 'local-campus', filter: kinds('walk'),
    paint: { 'line-color': '#aaa493', 'line-width': 1, 'line-opacity': .55, 'line-dasharray': [2, 2.5] } });
  map.addLayer({ id: 'buildings', type: 'fill', source: 'local-campus', filter: kinds('building'),
    paint: { 'fill-color': '#c9c6ba', 'fill-outline-color': '#aaa99f' } });

  const detailLabels: HTMLSpanElement[] = [];
  for (const { name, position } of data.landmarks) {
    const label = document.createElement('span');
    label.className = name === '九龙湖' ? 'map-label water-label' : 'map-label';
    label.textContent = name.replace('东南大学九龙湖校区', '');
    new Marker({ element: label, anchor: 'center' }).setLngLat([position[0], position[1]]).addTo(map);
    if (name === '桃园食堂' || name === '大学生活动中心') detailLabels.push(label);
  }
  const updateLabels = () => {
    for (const label of detailLabels) label.hidden = map.getZoom() < 16;
  };
  map.on('zoom', updateLabels);
  updateLabels();
}

export default function ReferenceMap({ exercise }: { exercise: ExerciseLayers | null }) {
  const target = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const current = useRef(exercise);
  current.current = exercise;
  const fitRef = useRef<() => void>(() => {});
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    if (!target.current) return;
    const container = target.current;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container, style: { version: 8, sources: {}, layers: [
          { id: 'ground', type: 'background', paint: { 'background-color': '#f0efe5' } },
        ] },
        center: [118.81558, 31.8909], zoom: 15, minZoom: 13.5, maxZoom: 19,
        maxBounds: mapBounds, pitchWithRotate: false, dragRotate: false,
        renderWorldCopies: false, attributionControl: false,
      });
    } catch {
      setStatus('error');
      return;
    }

    const controller = new AbortController();
    mapRef.current = map;
    fitRef.current = () => map.fitBounds(campusBounds, {
      padding: container.clientWidth > 580 ? 42 : 14, maxZoom: 16, duration: 0,
    });
    map.addControl(new NavigationControl(), 'top-right');
    map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left');
    const observer = new ResizeObserver(() => { map.resize(); fitRef.current(); });
    observer.observe(container);
    map.once('load', async () => {
      try {
        const response = await fetch(import.meta.env.BASE_URL + 'maps/jiulonghu.json', { signal: controller.signal });
        if (!response.ok) throw new Error('Reference map unavailable');
        const data: ReferenceData = await response.json();
        if (controller.signal.aborted) return;
        addReferenceLayers(map, data);
        addExerciseLayers(map, () => current.current);
        renderExercise(map, current.current);
        fitRef.current();
        map.once('idle', () => {
          if (controller.signal.aborted) return;
          const rendered = map.queryRenderedFeatures({ layers: ['buildings', 'streets', 'water'] });
          setStatus(rendered.length ? 'ready' : 'error');
        });
      } catch {
        if (!controller.signal.aborted) setStatus('error');
      }
    });
    map.on('error', () => setStatus('error'));
    return () => {
      controller.abort();
      observer.disconnect();
      mapRef.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getSource('roads')) renderExercise(map, exercise);
  }, [exercise]);

  return <div className="map-surface reference-surface">
    <div ref={target} className="map-canvas" aria-label="东南大学九龙湖校区地图" />
    {status === 'loading' && <p className="map-fallback" role="status">正在加载校园地图…</p>}
    {status === 'error' && <p className="map-fallback" role="status">
      地图渲染不可用。<a href={mapUrl} target="_blank" rel="noreferrer">在 OpenStreetMap 查看校区</a>
    </p>}
    <button className="map-reset" type="button" onClick={() => fitRef.current()} disabled={status !== 'ready'}>
      回到校区
    </button>
    <a className="map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
      © OpenStreetMap contributors
    </a>
  </div>;
}
