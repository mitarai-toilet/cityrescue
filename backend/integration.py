"""Single dispatch orchestration entry; providers receive isolated snapshots."""

from copy import deepcopy

from fastapi import HTTPException

from backend.dispatching import validate_inputs, validate_result
from backend.providers import invoke


class IntegrationService:
    def __init__(self, store, spatial_loader, dispatcher):
        self.store = store
        self.spatial_loader = spatial_loader
        self.dispatcher = dispatcher

    def dispatch(self, run_id, version, vehicles, events, *, previous_dispatch_index=None):
        snapshot = self.store.checked_snapshot(run_id, version)
        spatial = self.spatial_loader()
        validate_inputs(spatial, vehicles, events)
        arguments = (deepcopy(snapshot), deepcopy(spatial), deepcopy(vehicles), deepcopy(events))
        if previous_dispatch_index is None:
            result = invoke(self.dispatcher.dispatch, *arguments)
        else:
            replan = getattr(self.dispatcher, 'replan_active', None)
            if replan is None:
                raise HTTPException(501, detail={'code': 'provider_not_supported'})
            previous = self.store.dispatch_at(run_id, version, previous_dispatch_index)
            if previous['provider'] != self.dispatcher.name:
                raise HTTPException(409, detail={'code': 'dispatch_provider_conflict'})
            if any(event['status'] not in ('assigned', 'in_progress') for event in events):
                raise HTTPException(422, detail={'code': 'replan_requires_active_events'})
            result = invoke(replan, *arguments, previous['result'])
        result = deepcopy(result)
        validate_result(result, snapshot, spatial, vehicles, events)
        wrapped = {'provider': self.dispatcher.name, 'result': result}
        self.store.record_dispatch(run_id, version, wrapped)
        return wrapped
