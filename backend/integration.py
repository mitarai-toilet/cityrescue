"""Single dispatch orchestration entry; providers receive isolated snapshots."""

from copy import deepcopy

from backend.dispatching import validate_inputs, validate_result
from backend.providers import invoke


class IntegrationService:
    def __init__(self, store, spatial_loader, dispatcher):
        self.store = store
        self.spatial_loader = spatial_loader
        self.dispatcher = dispatcher

    def dispatch(self, run_id, version, vehicles, events):
        snapshot = self.store.checked_snapshot(run_id, version)
        spatial = self.spatial_loader()
        validate_inputs(spatial, vehicles, events)
        result = deepcopy(invoke(self.dispatcher.dispatch, deepcopy(snapshot), deepcopy(spatial),
                                 deepcopy(vehicles), deepcopy(events)))
        validate_result(result, snapshot, spatial, vehicles, events)
        wrapped = {'provider': self.dispatcher.name, 'result': result}
        self.store.record_dispatch(run_id, version, wrapped)
        return wrapped
