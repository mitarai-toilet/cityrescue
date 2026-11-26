import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.campus import DEFAULT_DATA, ROOT
from backend.dispatching import FixtureDispatchProvider
from backend.providers import ProviderError
from backend.simulation import FixtureSimulationProvider
from test_campus_api import server
from test_closure_dispatch_api import inputs


@pytest.mark.parametrize('component', ['simulation', 'dispatch'])
@pytest.mark.parametrize('failure,status', [('unexpected', 500), ('unavailable', 503), ('unsupported', 501),
                                         ('parameters', 400), ('schema', None), ('reference', None)])
def test_provider_failures_are_safe_and_preserve_existing_state(component, failure, status):
    fixture_sim = FixtureSimulationProvider(DEFAULT_DATA)
    fixture_dispatch = FixtureDispatchProvider()

    def fail():
        if failure == 'unexpected':
            raise RuntimeError('SECRET C:/private/credentials.key')
        if failure == 'unavailable':
            raise OSError('SECRET C:/private/credentials.key')
        if failure in ('unsupported', 'parameters'):
            raise ProviderError('SECRET', 501 if failure == 'unsupported' else 400)

    class Simulation:
        enabled = False

        def scenarios(self):
            return fixture_sim.scenarios()

        def replay(self, scenario):
            output = fixture_sim.replay(scenario)
            if self.enabled:
                fail()
                if failure == 'schema':
                    output.roads[0]['status'] = 'invalid'
                elif failure == 'reference':
                    output.roads[0]['road_id'] = 'missing-road'
                scenario['params'].clear()
            return output

    class Dispatch:
        name = 'failure-test'

        def dispatch(self, snapshot, spatial, vehicles, events):
            output = fixture_dispatch.dispatch(snapshot, spatial, vehicles, events)
            snapshot['roads'].clear()
            spatial['nodes'].clear()
            vehicles.clear()
            events.clear()
            fail()
            if failure == 'schema':
                output['outcome'] = 'invalid'
            elif failure == 'reference':
                output['assignments'][0]['vehicle_id'] = 'missing-vehicle'
            return output

    simulation = Simulation()
    app = create_app(simulation_provider=simulation, dispatch_provider=Dispatch())
    with TestClient(app) as client:
        run = client.post('/api/v1/simulation/runs', json={'scenario_id': 'SIM-FLOOD-01'}).json()['run_id']
        before = app.state.simulation_runs.get(run)
        if component == 'simulation':
            simulation.enabled = True
            response = client.post('/api/v1/simulation/runs', json={'scenario_id': 'SIM-FLOOD-01'})
        else:
            response = client.post('/api/v1/dispatch', json=inputs(run))
        expected = status if status is not None else (503 if component == 'simulation' else 502)
        assert response.status_code == expected
        assert 'code' in response.json()['detail']
        assert 'SECRET' not in response.text and 'credentials' not in response.text
        assert app.state.simulation_runs.get(run) == before
        assert app.state.simulation_runs.history(run)['dispatches'] == []
        assert len(app.state.simulation_runs._runs) == 1


def test_scenario_list_and_metadata_checked_at_shared_boundary():
    fixture = FixtureSimulationProvider(DEFAULT_DATA)

    class Provider:
        def scenarios(self):
            data = fixture.scenarios()
            data[0]['campus_id'] = 'missing-campus'
            return data

        def replay(self, scenario):
            raise AssertionError('Invalid scenario should be rejected before invocation')

    with TestClient(create_app(simulation_provider=Provider())) as client:
        assert client.get('/api/v1/scenarios').status_code == 503
        assert client.post('/api/v1/simulation/runs', json={'scenario_id': 'SIM-FLOOD-01'}).status_code == 503


def test_nonfixture_provider_context_is_not_labelled_as_fixture():
    fixture = FixtureSimulationProvider(DEFAULT_DATA)

    class Provider:
        def scenarios(self):
            return fixture.scenarios()

        def replay(self, scenario):
            # Test adapter only, not an actual real-world model.
            output = fixture.replay(scenario)
            output.mode = 'simulation'
            output.data_origin = 'estimated'
            output.provenance = ['test adapter']
            return output

    with TestClient(create_app(simulation_provider=Provider())) as client:
        response = client.post('/api/v1/simulation/runs', json={'scenario_id': 'SIM-FLOOD-01'})
        assert response.status_code == 201
        assert response.json()['mode'] == 'simulation' and response.json()['data_origin'] == 'estimated'


def test_powershell_demo_over_real_http():
    shell = shutil.which('pwsh') or shutil.which('powershell')
    assert shell, 'PowerShell is required to verify the delivered demo'
    with server(DEFAULT_DATA) as request:
        result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(ROOT / 'scripts/demo_backend.ps1'), '-BaseUrl', request.base_url],
                                capture_output=True, text=True, timeout=50)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'PASS:' in result.stdout and 'UNCOVERED:' in result.stdout
        print(result.stdout)
