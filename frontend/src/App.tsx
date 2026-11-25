import { useEffect, useRef, useState, type FormEvent } from 'react';
import ReferenceMap from './ReferenceMap';
import {
  ApiError, api, type Assignment, type ExerciseExamples, type Graph,
  type RescueEvent, type RoadStatus, type Scenario, type Snapshot,
} from './api';
import { applyDispatch, newBoard, readDraft, reserveVehicles, writeDraft } from './operations';

const statusNames: Record<RoadStatus, string> = { open: '正常', caution: '警戒', closed: '封闭' };
const originNames = { synthetic: '合成数据', estimated: '估算数据', real: '真实数据' };
const emptyAssignments: Assignment[] = [];
const taskStatus = { pending: '待处理', assigned: '已分配', in_progress: '执行中', completed: '已完成' };

interface CampusData {
  graph: Graph;
  examples: ExerciseExamples;
  scenarios: Scenario[];
}

function describeError(error: unknown) {
  if (!(error instanceof ApiError)) return '连接失败。检查调度后端是否运行，再重试。';
  const code = (error.detail as { code?: string } | null)?.code;
  switch (error.status) {
    case 404: return '运行或接口不可用。若后端已重启，请重新启动情景。';
    case 409: return '请求与当前道路状态或调度历史冲突。检查最新状态后重试。';
    case 422: return '调度输入不符合契约。检查任务、车辆位置和任务状态。';
    case 501: return '当前后端未启用此调度能力。请使用 D 分支的调度入口。';
    case 503: return '后端数据或仿真服务暂不可用。检查服务后重试。';
    default: return `请求失败（HTTP ${error.status}${code ? ` · ${code}` : ''}）。请检查后端。`;
  }
}

function eta(value: number | null) {
  return value === null ? '无 ETA' : `${value.toFixed(2)} 分钟`;
}

function routeReason(reason?: string | null) {
  if (reason === 'no_route_after_replan' || reason === 'unreachable') return '当前路网没有可通行路线';
  return reason || '当前路网没有可通行路线';
}

function App() {
  const [data, setData] = useState<CampusData | null>(null);
  const [scenarioId, setScenarioId] = useState('');
  const [run, setRun] = useState<Snapshot | null>(null);
  const [draft] = useState(readDraft);
  const [showExercise, setShowExercise] = useState(true);
  const [runId, setRunId] = useState(draft?.runId ?? null);
  const [board, setBoard] = useState(() => draft?.board ?? newBoard());
  const { vehicles, events, results } = board;
  const [needsSync, setNeedsSync] = useState(Boolean(draft));
  const [confirmStart, setConfirmStart] = useState(false);
  const [roadId, setRoadId] = useState('');
  const [manualRoads, setManualRoads] = useState<string[]>([]);
  const [nodeId, setNodeId] = useState('');
  const [priority, setPriority] = useState(1);
  const [demand, setDemand] = useState(1);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [activeNode, setActiveNode] = useState('');
  const [unavailable, setUnavailable] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function refreshRun(runId: string) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const [state, history] = await Promise.all([api.state(runId), api.history(runId)]);
      if ((history.changes.at(-1)?.state_version ?? 0) !== state.state_version) continue;
      setRun(state);
      const closed = new Set<string>();
      for (const change of history.changes) {
        if (change.action === 'close') closed.add(change.road_id);
        else closed.delete(change.road_id);
      }
      setManualRoads([...closed]);
      setNeedsSync(false);
      return { state, history };
    }
    throw new ApiError(409, { code: 'snapshot_history_conflict' });
  }

  async function recoverRun(id: string) {
    const { state, history } = await refreshRun(id);
    // A dispatch may have committed even when its HTTP response was interrupted.
    setBoard((existing) => {
      const pending = new Set(existing.events.filter((event) => event.status === 'pending').map((event) => event.event_id));
      let next = existing;
      for (const record of history.dispatches) {
        const recovered = record.result.assignments.filter((assignment) =>
          assignment.outcome === 'assigned' && pending.delete(assignment.event_id));
        if (recovered.length) {
          next = applyDispatch(next, { ...record, result: { ...record.result, assignments: recovered, unassigned_events: [] } }, []);
        }
      }
      return next;
    });
    return state;
  }

  async function perform(action: () => Promise<void>, updatesRun = false) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setNotice('');
    setError('');
    try {
      await action();
    } catch (caught) {
      if (updatesRun && (!(caught instanceof ApiError) || [404, 409, 500, 502, 503, 504].includes(caught.status))) {
        setNeedsSync(true);
        if (runId && caught instanceof ApiError && caught.status === 409) {
          await recoverRun(runId).catch(() => {});
        }
      }
      setError(describeError(caught));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function loadCampus() {
    return perform(async () => {
      const [graph, examples, scenarios] = await Promise.all([api.graph(), api.examples(), api.scenarios()]);
      setData({ graph, examples, scenarios });
      setScenarioId(scenarios[0]?.scenario_id ?? '');
      setNodeId(graph.nodes[0]?.node_id ?? '');
      setRoadId(graph.roads[0]?.road_id ?? '');
      if (runId) {
        const restored = await recoverRun(runId);
        setScenarioId(restored.scenario_id);
        setNotice('已恢复此标签页的演示任务，并同步后端路网。');
      }
    });
  }

  useEffect(() => { void loadCampus(); }, []);
  useEffect(() => { writeDraft(runId, board); }, [runId, board]);

  function startRun() {
    if (!data) return;
    return perform(async () => {
      const created = await api.start(scenarioId);
      setRunId(created.run_id);
      setRun(null);
      setNeedsSync(true);
      setBoard(newBoard(data.examples.vehicles));
      setFocusedId(null);
      setShowExercise(true);
      setConfirmStart(false);
      setUnavailable(false);
      await refreshRun(created.run_id);
      setNotice('灾害情景已启动。可添加求救任务或载入演示任务。');
    });
  }

  function syncRun() {
    if (!runId) return;
    return perform(async () => {
      setNeedsSync(true);
      await recoverRun(runId);
      setNotice('当前运行已同步。');
    });
  }

  function addEvent(event: FormEvent) {
    event.preventDefault();
    if (!run || !nodeId || busy || needsSync) return;
    setBoard((existing) => {
      const id = existing.events.filter((item) => item.event_id.startsWith('B-E')).length + 1;
      return { ...existing, events: [...existing.events,
        { event_id: `B-E${id}`, node_id: nodeId, priority, demand, status: 'pending' }] };
    });
    setNotice('求救任务已添加。');
  }

  function loadFixture() {
    if (!data) return;
    setBoard((existing) => ({ ...existing, events: [...existing.events, ...fixtureTasks.filter((task) =>
      !existing.events.some((event) => event.event_id === task.event_id))] }));
    setNotice('已在校区路网上载入三项模拟求救任务。');
  }

  function changeRoad(close: boolean) {
    if (!run || !roadId || needsSync) return;
    return perform(async () => {
      await api.changeRoad(run, roadId, close);
      setNeedsSync(true);
      const { state } = await refreshRun(run.run_id);
      const status = state.roads.find((road) => road.road_id === roadId)?.status;
      setNotice(`${roadId} · ${status ? statusNames[status] : '状态已更新'}。${
        Object.values(results).some((result) => result.version !== state.state_version)
          ? '可按新版本重新调度或重规划。' : ''
      }`);
    }, true);
  }

  function dispatchPending() {
    if (!run || needsSync) return;
    return perform(async () => {
      const candidates = reserveVehicles(board, run.time_min, unavailable);
      const next = await api.dispatch(run, candidates, events.filter((event) => event.status === 'pending'));
      setBoard((existing) => applyDispatch(existing, next, candidates,
        candidates.every((vehicle) => vehicle.available_at_min > run.time_min)));
      setNotice('调度结果已更新。');
    }, true);
  }

  function focusTask(id: string | null) {
    setFocusedId(id);
    if (id) setShowExercise(true);
    const vehicleId = id ? results[id]?.assignment?.vehicle_id : undefined;
    setActiveNode(vehicles.find((vehicle) => vehicle.vehicle_id === vehicleId)?.node_id ?? '');
  }

  function changeTask(id: string, status: 'in_progress' | 'completed') {
    const task = events.find((event) => event.event_id === id);
    const assignment = results[id]?.assignment;
    if (!task || !assignment || needsSync || (status === 'completed' &&
      (task.status !== 'in_progress' || assignment.outcome !== 'assigned' ||
        results[id].version !== run?.state_version))) return;
    if (status === 'in_progress' && (task.status !== 'assigned' ||
      results[id].version !== run?.state_version)) return;
    setBoard((existing) => ({
      ...existing,
      events: existing.events.map((event) => event.event_id === id ? { ...event, status } : event),
      vehicles: status === 'completed' ? existing.vehicles.map((vehicle) =>
        vehicle.vehicle_id === assignment.vehicle_id ? { ...vehicle, node_id: task.node_id } : vehicle) : existing.vehicles,
    }));
    focusTask(id);
    setNotice(status === 'completed' ? '任务已完成，车辆已在求救节点释放。' : '任务已开始，车辆继续保持占用。');
    setError('');
  }

  const focusedTask = events.find((event) => event.event_id === focusedId);
  const focusedResult = focusedId ? results[focusedId] : undefined;
  const active = focusedTask?.status === 'assigned' || focusedTask?.status === 'in_progress'
    ? focusedResult?.assignment : undefined;

  function replan() {
    if (!run || !active || !activeNode || !focusedTask || needsSync) return;
    return perform(async () => {
      const { state, history } = await refreshRun(run.run_id);
      if (state.state_version !== run.state_version) {
        setError('道路状态已更新。请确认最新状态后重试。');
        return;
      }
      const matchesActive = (assignment: Assignment) =>
        assignment.event_id === active.event_id && assignment.vehicle_id === active.vehicle_id;
      const index = history.dispatches.findLastIndex((record) =>
        record.result.state_version < state.state_version && record.result.assignments.some(matchesActive));
      if (index < 0) {
        setError('找不到更早道路版本的车辆分配。请先完成调度，再变更道路状态。');
        return;
      }
      const confirmed = vehicles.map((vehicle) => vehicle.vehicle_id === active.vehicle_id
        ? { ...vehicle, node_id: activeNode } : vehicle);
      const next = await api.dispatch(state, confirmed, [focusedTask], index);
      setBoard((existing) => applyDispatch({ ...existing, vehicles: confirmed }, next, confirmed));
      const assignment = next.result.assignments.find(matchesActive);
      if (assignment?.outcome === 'unreachable') setError('当前路网不可达。可调整道路状态后再次重规划。');
      else setNotice('任务路线已更新。');
    }, true);
  }

  const taskResults = Object.entries(results);
  const eventById = new Map(events.map((event) => [event.event_id, event]));
  const mapResults = taskResults.filter(([id]) => eventById.get(id)?.status !== 'completed');
  const currentRoutes = mapResults.flatMap(([, result]) =>
    result.version === run?.state_version && result.assignment ? [result.assignment] : emptyAssignments);
  const previousRoutes = mapResults.flatMap(([, result]) => {
    const route = result.version === run?.state_version ? result.previous?.assignment : result.assignment;
    return route ? [route] : emptyAssignments;
  });
  const pending = events.filter((event) => event.status === 'pending');
  const fixtureTasks = data?.examples.events ?? [];
  const road = run?.roads.find((item) => item.road_id === roadId);
  const canReplan = Boolean(run && active && activeNode && focusedResult && !needsSync &&
    focusedResult.version < run.state_version);

  return (
    <>
      <header className="topbar">
        <div className="identity">
          <a className="brand" href={import.meta.env.BASE_URL} aria-label="CITYRESCUE 工作台首页">CITY<span>RESCUE</span></a>
          <h1>校园应急调度</h1>
        </div>
        <div className="top-meta">
          <span className="run-state" data-running={Boolean(run && !needsSync)}>
            {needsSync ? '等待同步路网' : run ? `演练进行中 · 第 ${run.time_min} 分钟 · 路网 v${run.state_version}` : '演练未启动'}
          </span>
        </div>
      </header>
        <main className="workspace">
          <section className="map-panel" aria-labelledby="map-title">
            <div className="map-heading">
              <div>
                <h2 id="map-title">东南大学九龙湖校区</h2>
                <p>江苏 · 南京 · 江宁区</p>
              </div>
              {run && <label className="checkbox layer-switch"><input type="checkbox" checked={showExercise}
                onChange={(event) => setShowExercise(event.target.checked)} />显示演练图层</label>}
            </div>
            <ReferenceMap exercise={run && data && showExercise ? {
              graph: data.graph, run, vehicles, events: events.filter((event) => event.status !== 'completed'),
              current: needsSync ? emptyAssignments : currentRoutes,
              previous: needsSync ? [...previousRoutes, ...currentRoutes] : previousRoutes,
              focusedTaskId: focusedId, focusedVehicleId: focusedResult?.assignment?.vehicle_id,
              roadId, nodeId, onRoad: setRoadId, onNode: setNodeId, onTask: focusTask,
            } : null} />
            <div className="map-context">
              <span>OpenStreetMap 校园地理</span>
              <span>{run ? '灾情、封路及调度结果均为演练数据' : '启动情景后在同一张地图上显示演练数据'}</span>
            </div>
            {run && showExercise && <div className="legend" aria-label="演练图例">
              <span><i className="key open" />正常</span>
              <span><i className="key caution" />警戒</span>
              <span><i className="key closed" />封闭</span>
              <span><i className="key vehicle" />救援车辆</span>
              <span><i className="key event" />求救点</span>
              <span><i className="key current" />当前路线</span>
              <span><i className="key previous" />旧路线</span>
            </div>
            }
            {run &&
            <section className="results" aria-labelledby="result-title">
              <div className="result-header">
                <h2 id="result-title">调度结果</h2>
                {run && <span>当前路网 v{run.state_version}</span>}
              </div>
              {taskResults.length === 0 && <p className="muted">完成首次调度后，这里会显示车辆分配、路线和 ETA。</p>}
              {taskResults.map(([id, { assignment, startNode, previous: old, version, noVehicles }]) => {
                const task = eventById.get(id);
                const stale = needsSync || version !== run?.state_version;
                const versionNote = stale ? ` · 路网 v${version} 的结果已过期` : '';
                if (!assignment) return <p className="unassigned" key={id}>
                  未分配：{id}{noVehicles ? ' · 当前所有车辆暂不可用' : ' · 请核对车辆可用性和路网连通性'}{versionNote}
                </p>;
                return <article className={`result${focusedId === id ? ' selected' : ''}`} key={id}>
                  <div>
                    <button type="button" className="result-focus" aria-pressed={focusedId === id}
                      onClick={() => focusTask(focusedId === id ? null : id)}>
                      {assignment.event_id} · {assignment.vehicle_id}
                    </button>
                    {task && <span className="task-state">{taskStatus[task.status]}</span>}
                    {startNode && task && <p className="muted">起点 {startNode} → 求救点 {task.node_id}</p>}
                    <p>{assignment.outcome === 'unreachable' ? routeReason(assignment.reason)
                      : assignment.road_ids.length ? `路线共 ${assignment.road_ids.length} 段` : '车辆已在求救节点'}</p>
                    {old && <p className="muted">旧路线 v{old.version}{old.startNode ? ` · 起点 ${old.startNode}` : ''}
                      {' · '}{old.assignment.road_ids.length} 段 · {eta(old.assignment.eta_min)}</p>}
                    {!stale && task?.status !== 'completed' && assignment.road_ids.length > 0 && <label className="route-picker">
                      查看路线上的路段
                      <select value={assignment.road_ids.includes(roadId) ? roadId : ''}
                        onChange={(event) => {
                          if (event.target.value) {
                            focusTask(id);
                            setRoadId(event.target.value);
                          }
                        }}>
                        <option value="" disabled>选择路段</option>
                        {assignment.road_ids.map((routeId, index) => <option key={routeId} value={routeId}>
                          {index + 1}. {routeId}
                        </option>)}
                      </select>
                    </label>}
                    {stale && <p className="muted">路网 v{version} 的结果已过期</p>}
                  </div>
                  <div className="result-action">
                    <strong>{eta(assignment.eta_min)}</strong>
                    {task?.status === 'assigned' && <button type="button" disabled={busy || stale || assignment.outcome === 'unreachable'}
                      onClick={() => changeTask(id, 'in_progress')}>开始执行</button>}
                    {task?.status === 'in_progress' && <button type="button" disabled={busy || stale || assignment.outcome === 'unreachable'}
                      onClick={() => changeTask(id, 'completed')}>标记完成</button>}
                  </div>
                </article>;
              })}
            </section>
            }
          </section>
          <aside className="controls" aria-label="调度操作" aria-busy={busy}>
            <header className="controls-heading">
              <h2>演练控制</h2>
              <p>{run ? '管理任务、道路和车辆' : '演练沿校区道路进行'}</p>
            </header>
            {!data ? (
              <section className="connection-status">
                {error ? <><p role="alert">{error}</p><button onClick={loadCampus}>重试连接</button></>
                  : <p role="status">正在连接调度后端…</p>}
              </section>
            ) : <>
            <section>
              <h2>灾害情景</h2>
              <div className="row">
                <select aria-label="灾害情景" value={scenarioId} disabled={busy} onChange={(event) => setScenarioId(event.target.value)}>
                  {data.scenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>
                    {scenario.hazard_type === 'flood' ? '洪涝' : '地震'} · {scenario.scenario_id}
                  </option>)}
                </select>
                <button type="button" className={!runId ? 'primary' : ''} onClick={() => runId && events.length
                  ? setConfirmStart(true) : void startRun()} disabled={busy || !scenarioId}>
                  {runId ? '启动新情景' : '启动情景'}
                </button>
              </div>
              {run && <p className="muted">{run.scenario_id} · {run.mode === 'fixture_replay' ? '固定情景回放' : '仿真'} · {originNames[run.data_origin]}</p>}
              {confirmStart && <div className="feedback">
                <p>启动新情景会清除当前标签页中的任务和路线。</p>
                <div className="row equal">
                  <button type="button" onClick={startRun} disabled={busy}>确认启动</button>
                  <button type="button" onClick={() => setConfirmStart(false)} disabled={busy}>保留当前情景</button>
                </div>
              </div>}
              {runId && <button type="button" className="link-button" onClick={syncRun} disabled={busy}>重新同步当前运行</button>}
              {needsSync && <p className="muted">路网状态待同步。同步后可继续操作；若后端已重启，可启动新情景。</p>}
            </section>
            {!run && <section className="reference-key" aria-label="真实地图图例">
              <h2>地图图例</h2>
              <ul>
                <li><i className="map-swatch street" />道路</li>
                <li><i className="map-swatch building" />建筑</li>
                <li><i className="map-swatch water" />水体</li>
                <li><i className="map-swatch green" />绿地与运动场</li>
              </ul>
              <a href="https://www.openstreetmap.org/way/171389014" target="_blank" rel="noreferrer">查看 OpenStreetMap 原图</a>
            </section>}
            {run && <>
            <section>
              <h2>求救任务</h2>
              <form onSubmit={addEvent}>
                <fieldset disabled={!run || busy || needsSync}>
                  <label className="wide">求救节点
                    <select value={nodeId} onChange={(event) => setNodeId(event.target.value)}>
                      {data.graph.nodes.map((node) => <option key={node.node_id}>{node.node_id}</option>)}
                    </select>
                  </label>
                  <label>优先级
                    <select value={priority} onChange={(event) => setPriority(Number(event.target.value))}>
                      {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value === 1 ? '1 · 最紧急' : value}</option>)}
                    </select>
                  </label>
                  <label>需求量
                    <input type="number" required min="1" step="1" value={demand || ''}
                      onChange={(event) => setDemand(Number(event.target.value))} />
                  </label>
                  <button type="submit" className="wide">添加求救任务</button>
                </fieldset>
              </form>
              <button type="button" className="link-button" onClick={loadFixture}
                disabled={!run || busy || needsSync || fixtureTasks.every((task) => events.some((event) => event.event_id === task.event_id))}>
                载入三项演示任务
              </button>
              {events.length > 0 && <ul className="task-list">
                {events.map((event) => <li key={event.event_id}>
                  <button type="button" className="result-focus" aria-pressed={focusedId === event.event_id}
                    onClick={() => focusTask(focusedId === event.event_id ? null : event.event_id)}>{event.event_id}</button>
                  <span>{event.node_id} · P{event.priority} · 需求 {event.demand} · {taskStatus[event.status]}</span>
                </li>)}
              </ul>}
            </section>
            <section>
              <h2>道路管制</h2>
              <label>路段
                <select value={roadId} disabled={!run || busy || needsSync} onChange={(event) => setRoadId(event.target.value)}>
                  {data.graph.roads.map((item) => <option key={item.road_id}>{item.road_id}</option>)}
                </select>
              </label>
              {road && <p className={`muted road-status ${road.status}`}>
                {statusNames[road.status]}{manualRoads.includes(roadId) ? ' · 人工封路' : ''}
                {road.depth_m !== null ? ` · 水深 ${road.depth_m} m` : ''}
              </p>}
              <div className="row equal">
                <button type="button" onClick={() => changeRoad(true)} disabled={busy || needsSync || !road || manualRoads.includes(roadId)}>封闭道路</button>
                <button type="button" onClick={() => changeRoad(false)} disabled={busy || needsSync || !manualRoads.includes(roadId)}>撤销人工封路</button>
              </div>
            </section>
            <section>
              <h2>车辆调度</h2>
              {run && <ul className="task-list">{reserveVehicles(board, run.time_min, unavailable).map((vehicle) =>
                <li key={vehicle.vehicle_id}><strong>{vehicle.vehicle_id}</strong>
                  <span>{vehicle.node_id} · {vehicle.available_at_min > run.time_min ? '不可调度' : '可调度'}</span></li>)}</ul>}
              <label className="checkbox"><input type="checkbox" checked={unavailable} disabled={!run || busy || needsSync}
                onChange={(event) => setUnavailable(event.target.checked)} />模拟车辆全部不可用</label>
              {active && <label>{active.vehicle_id} 的确认节点
                <select value={activeNode} onChange={(event) => setActiveNode(event.target.value)} disabled={busy || needsSync}>
                  {data.graph.nodes.map((node) => <option key={node.node_id}>{node.node_id}</option>)}
                </select>
              </label>}
              <div className="row equal">
                <button type="button" className={!canReplan ? 'primary' : ''} onClick={dispatchPending}
                  disabled={!run || busy || needsSync || pending.length === 0}>调度待处理任务</button>
                {active && <button type="button" className={canReplan ? 'primary' : ''} onClick={replan}
                  disabled={busy || !canReplan}>重规划 {active.event_id}</button>}
              </div>
            </section>
            </>}
            {(notice || error || busy) && <div className={error ? 'feedback error' : 'feedback'} role={error ? 'alert' : 'status'}>
              {busy ? '正在请求后端…' : error || notice}
            </div>}
            </>}
          </aside>
        </main>
    </>
  );
}

export default App;
