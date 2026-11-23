"""Deterministic, risk-aware rescue dispatch using the frozen v0.1 entities."""

from math import isfinite

import networkx as nx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from backend.campus import entity_schema
from backend.providers import ProviderError


class NetworkXDispatchProvider:
    name = 'networkx_dispatch_v1'

    def __init__(self, required_capabilities=None):
        # Event v0.1 has no capability requirement field. E may supply an explicit
        # event-to-capability policy without changing the frozen public entities.
        self.required_capabilities = {
            event_id: frozenset(labels)
            for event_id, labels in (required_capabilities or {}).items()
        }

    def dispatch(self, snapshot, spatial, vehicles, events):
        validators = {
            name: Draft202012Validator(entity_schema(name))
            for name in ('node', 'road', 'road_state', 'vehicle', 'event')
        }
        collections = (
            ('node', spatial['nodes']), ('road', spatial['roads']),
            ('road_state', snapshot['roads']), ('vehicle', vehicles), ('event', events),
        )
        for entity, items in collections:
            ids = set()
            for item in items:
                try:
                    validators[entity].validate(item)
                except ValidationError as exc:
                    raise ProviderError('invalid_dispatch_entity', 400) from exc
                key = 'road_id' if entity == 'road_state' else entity + '_id'
                if item[key] in ids:
                    raise ProviderError('duplicate_dispatch_id', 400)
                ids.add(item[key])

        nodes = {node['node_id'] for node in spatial['nodes']}
        states = {state['road_id']: state for state in snapshot['roads']}
        if set(states) != {road['road_id'] for road in spatial['roads']}:
            raise ProviderError('incomplete_road_snapshot', 400)
        for state in states.values():
            if (state['time_min'] != snapshot['time_min']
                    or state.get('state_version', snapshot['state_version']) != snapshot['state_version']):
                raise ProviderError('inconsistent_road_snapshot', 400)
        if any(item['node_id'] not in nodes for item in [*vehicles, *events]):
            raise ProviderError('invalid_dispatch_node', 400)

        graph = nx.MultiDiGraph()
        graph.add_nodes_from(sorted(nodes))
        for road in sorted(spatial['roads'], key=lambda item: item['road_id']):
            start, end = road['from_node'], road['to_node']
            if start not in nodes or end not in nodes:
                raise ProviderError('invalid_road_endpoint', 400)
            state = states[road['road_id']]
            if state['status'] == 'closed':
                continue
            travel = road['length_m'] / road['speed_kmh'] * 0.06
            cost = travel + state['risk_penalty_min']
            if not isfinite(cost) or travel <= 0:
                raise ProviderError('invalid_road_cost', 400)
            graph.add_edge(start, end, key=road['road_id'], travel=travel, cost=cost)
            if not road['one_way']:
                graph.add_edge(end, start, key=road['road_id'], travel=travel, cost=cost)

        available = {
            vehicle['vehicle_id']: vehicle for vehicle in vehicles
            if vehicle['available_at_min'] <= snapshot['time_min']
        }
        assignments, unassigned = [], []
        for event in sorted(events, key=lambda item: (item['priority'], item['event_id'])):
            event_id = event['event_id']
            if event['status'] != 'pending':
                unassigned.append(event_id)
                continue
            required = self.required_capabilities.get(event_id, frozenset())
            candidates = []
            for vehicle_id, vehicle in sorted(available.items()):
                if not required.issubset(vehicle['capability']):
                    continue
                try:
                    cost, node_path = nx.single_source_dijkstra(
                        graph, vehicle['node_id'], event['node_id'], weight='cost',
                    )
                except nx.NetworkXNoPath:
                    continue
                road_ids, eta = [], 0.0
                for start, end in zip(node_path, node_path[1:]):
                    road_id, edge = min(
                        graph[start][end].items(), key=lambda pair: (pair[1]['cost'], pair[0]),
                    )
                    road_ids.append(road_id)
                    eta += edge['travel']
                if not isfinite(cost) or not isfinite(eta):
                    raise ProviderError('invalid_route_cost', 400)
                candidates.append((cost, vehicle_id, road_ids, eta))
            if not candidates:
                unassigned.append(event_id)
                continue
            _, vehicle_id, road_ids, eta = min(candidates)
            assignments.append({
                'event_id': event_id, 'vehicle_id': vehicle_id, 'road_ids': road_ids,
                'eta_min': eta, 'outcome': 'assigned',
            })
            del available[vehicle_id]

        outcome = 'complete'
        if unassigned:
            outcome = 'partial' if assignments else 'unreachable'
        return {
            'run_id': snapshot['run_id'], 'state_version': snapshot['state_version'],
            'assignments': assignments, 'unassigned_events': unassigned, 'outcome': outcome,
        }
