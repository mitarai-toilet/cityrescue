param([string]$BaseUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
if (([uri]$BaseUrl).Host -notin @('127.0.0.1', 'localhost', '::1')) {
    throw 'The demo requires a local loopback server'
}
# Local verification must not be routed through a system HTTP proxy.
$originalProxy = [System.Net.WebRequest]::DefaultWebProxy
[System.Net.WebRequest]::DefaultWebProxy = $null

function Send-Api {
    param([string]$Path, [string]$Method = 'GET', $Body = $null, [int]$Expected = 200)
    $options = @{ Uri = "$BaseUrl$Path"; Method = $Method; UseBasicParsing = $true; TimeoutSec = 5 }
    if ((Get-Command Invoke-WebRequest).Parameters.ContainsKey('NoProxy')) { $options.NoProxy = $true }
    if ($null -ne $Body) {
        $options.ContentType = 'application/json'
        $options.Body = $Body | ConvertTo-Json -Depth 30 -Compress
    }
    try {
        $response = Invoke-WebRequest @options
        $status = [int]$response.StatusCode
        $content = $response.Content
    } catch {
        if ($null -eq $_.Exception.Response) { throw }
        $status = [int]$_.Exception.Response.StatusCode
        if ($status -ne $Expected) { throw "HTTP $status for $Method $Path (expected $Expected)" }
        $content = $_.ErrorDetails.Message
    }
    if ($status -ne $Expected) { throw "Unexpected HTTP $status for $Method $Path (expected $Expected)" }
    if ($Expected -eq 409) { return }
    return $content | ConvertFrom-Json
}

try {
    $health = Send-Api '/health'
    if ($health.status -ne 'ok') { throw 'Health check failed' }
    $campus = Send-Api '/api/v1/campus'
    if ($campus.data_origin -ne 'synthetic') { throw 'This demonstration requires the default synthetic campus' }
    $scenarios = @(Send-Api '/api/v1/scenarios')
    $scenario = $scenarios | Where-Object hazard_type -eq 'flood' | Select-Object -First 1
    if ($null -eq $scenario) { throw 'A fixed flood scenario is required' }
    $roads = @(Send-Api '/api/v1/campus/roads')
    $repo = Split-Path -Parent $PSScriptRoot
    $fixture = Join-Path $repo 'data/fixtures/synthetic_campus'
    $vehicles = @(Get-Content -LiteralPath (Join-Path $fixture 'vehicles.json') -Raw | ConvertFrom-Json)
    $events = @(Get-Content -LiteralPath (Join-Path $fixture 'events.json') -Raw | ConvertFrom-Json)
    $cases = @(Get-Content -LiteralPath (Join-Path $repo 'backend/fixtures/dispatch_cases.json') -Raw | ConvertFrom-Json)
    $roadId = ($cases | Where-Object { $null -ne $_.manual_closed_road } | Select-Object -First 1).manual_closed_road
    if (-not ($roads | Where-Object road_id -eq $roadId)) { throw 'Fixed closure case does not match the loaded campus' }
    $run = Send-Api '/api/v1/simulation/runs' 'POST' @{ scenario_id = $scenario.scenario_id } 201
    $root = "/api/v1/simulation/runs/$($run.run_id)"
    $state = Send-Api "$root/state"
    $dispatch = @{run_id = $run.run_id; state_version = $state.state_version; vehicles = @($vehicles[0]); events = @($events[0])}
    $initial = Send-Api '/api/v1/dispatch' 'POST' $dispatch
    if ($initial.provider -ne 'fixture_dispatch') { throw 'This script verifies fixture dispatch only' }
    $change = Send-Api "$root/roads/$roadId/close" 'POST' @{state_version = $state.state_version}
    if (-not $change.changed -or $change.state_version -ne ($state.state_version + 1)) { throw 'Closure version did not advance' }
    Send-Api "$root/roads/$roadId/open" 'POST' @{state_version = $state.state_version} 409
    $latest = Send-Api "$root/state"
    if ($latest.state_version -ne $change.state_version) { throw 'Conflict altered state' }
    if (($latest.roads | Where-Object road_id -eq $roadId).status -ne 'closed') { throw 'Road closure not retained' }
    $dispatch.state_version = $latest.state_version
    $result = Send-Api '/api/v1/dispatch' 'POST' $dispatch
    if ($result.result.run_id -ne $run.run_id -or $result.result.state_version -ne $latest.state_version) { throw 'Dispatch identity mismatch' }
    if ($result.result.assignments[0].road_ids -contains $roadId) { throw 'Dispatch used closed road' }
    Write-Output "PASS: health, campus, scenarios, run=$($run.run_id), closure, version increment, HTTP 409, fixed dispatch"
    Write-Output 'UNCOVERED: real disaster calculation, real dispatch/replanning, frontend, real campus validation.'
    Write-Output 'This script created a dedicated in-memory run only; it did not edit source fixtures or previous runs.'
    exit 0
} catch {
    Write-Error "DEMO FAILED: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
} finally {
    [System.Net.WebRequest]::DefaultWebProxy = $originalProxy
}
