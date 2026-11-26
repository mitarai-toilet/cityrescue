async (page) => {
  const verify = (condition, message) => { if (!condition) throw new Error(message); };
  const button = (name) => page.getByRole('button', { name, exact: true });
  const select = (name) => page.getByRole('combobox', { name, exact: true });
  const resultRow = (id) => page.locator('.result').filter({ hasText: id });
  const taskRow = (id) => page.getByRole('complementary', { name: '调度操作' })
    .getByRole('listitem').filter({ has: button(id) });
  const path = (suffix) => new URL('/api/v1' + suffix, page.url()).href;
  async function post(action, suffix, expected = 200) {
    const [response] = await Promise.all([
      page.waitForResponse((item) => item.request().method() === 'POST' &&
        new URL(item.url()).pathname.endsWith(suffix)),
      action(),
    ]);
    verify(response.status() === expected, suffix + ' returned ' + response.status());
    return response.json();
  }

  const capture = new URL(page.url()).searchParams.has('capture');
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.reload();
  await page.getByRole('heading', { name: '东南大学九龙湖校区' }).waitFor();
  await button('回到校区').click();
  const canvas = await page.locator('.map-canvas canvas').elementHandle();
  await page.getByRole('link', { name: '© OpenStreetMap contributors' }).waitFor();
  if (capture) await page.screenshot({ path: 'output/playwright/cityrescue-b-campus.png' });

  const campus = await page.request.get(path('/campus/graph')).then((response) => response.json());
  const examples = await page.request.get(path('/exercise/examples')).then((response) => response.json());
  const osm = await page.request.get(new URL('/maps/jiulonghu.json', page.url()).href).then((response) => response.json());
  const coordsKey = (a, b) => [a.join(','), b.join(',')].sort().join('|');
  const segments = new Set(osm.features.filter((feature) => feature.geometry.type === 'LineString')
    .flatMap(({ geometry }) => geometry.coordinates.slice(1).map((point, index) => coordsKey(point, geometry.coordinates[index]))));
  for (const { geometry, road_id } of campus.roads) {
    verify(geometry.coordinates.slice(1).every((point, index) => segments.has(coordsKey(point, geometry.coordinates[index]))),
      road_id + ' contains a segment missing from the OSM basemap');
  }
  const run = await post(() => button('启动情景').click(), '/simulation/runs', 201);
  verify(await canvas.evaluate((element) => element.isConnected), 'Starting the exercise replaced the real map canvas');
  await page.getByRole('checkbox', { name: '显示演练图层' }).uncheck();
  await page.getByRole('link', { name: '© OpenStreetMap contributors' }).waitFor();
  await page.getByRole('checkbox', { name: '显示演练图层' }).check();
  await button('载入三项演示任务').click();
  const initial = await post(() => button('调度待处理任务').click(), '/dispatch');
  verify(initial.provider === 'networkx_dispatch_v1', 'Expected the NetworkX provider');
  verify(initial.result.assignments.length === 2 && initial.result.unassigned_events.length === 1,
    'Expected two assignments and one unassigned task');
  const [first, other] = initial.result.assignments;
  const start = examples.vehicles.find((vehicle) => vehicle.vehicle_id === first.vehicle_id).node_id;
  const target = examples.events.find((event) => event.event_id === first.event_id).node_id;
  verify(first.road_ids.length > 1, 'Expected a route with multiple OSM road sections');
  await taskRow(first.event_id).getByText('已分配', { exact: false }).waitFor();
  if (capture) {
    await page.setViewportSize({ width: 1440, height: 1560 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'output/playwright/cityrescue-b-before.png' });
  }

  await select('求救节点').selectOption(target);
  await button('添加求救任务').click();
  const queued = await post(() => button('调度待处理任务').click(), '/dispatch');
  verify(!queued.result.assignments.length && queued.result.unassigned_events.includes('B-E1'),
    'Busy vehicles must not be assigned to the fourth task');
  await page.reload();
  await page.getByText('已恢复此标签页的演示任务', { exact: false }).waitFor();
  await taskRow('B-E1').getByText('待处理', { exact: false }).waitFor();

  await resultRow(first.event_id).getByRole('button', { name: '开始执行' }).click();
  await resultRow(other.event_id).getByRole('button', { name: '开始执行' }).click();
  await taskRow(first.event_id).getByText('执行中', { exact: false }).waitFor();
  await taskRow(other.event_id).getByText('执行中', { exact: false }).waitFor();
  const closingRoad = first.road_ids[1];
  await resultRow(first.event_id).getByRole('combobox', { name: '查看路线上的路段' }).selectOption(closingRoad);
  verify(await select('路段').inputValue() === closingRoad, 'Selected route section did not appear in road controls');
  verify(await select(first.vehicle_id + ' 的确认节点').inputValue() === start, 'Expected the same origin for the route comparison');

  const stateUrl = path('/simulation/runs/' + run.run_id + '/state');
  const interrupt = (route) => route.abort();
  await page.route(stateUrl, interrupt, { times: 1 });
  const closed = await post(() => button('封闭道路').click(), '/roads/' + closingRoad + '/close');
  verify(closed.state_version === 1 && closed.road.status === 'closed', 'Expected versioned closure');
  await page.getByText('等待同步路网').waitFor();
  verify(await button('重规划 ' + first.event_id).isDisabled(), 'Replanning must wait for synchronization');
  await button('重新同步当前运行').click();
  await page.getByText('封闭 · 人工封路', { exact: false }).waitFor();
  const after = await post(() => button('重规划 ' + first.event_id).click(), '/dispatch/replan');
  const rerouted = after.result.assignments[0];
  verify(rerouted.vehicle_id === first.vehicle_id && after.result.state_version === 1 &&
    rerouted.road_ids.length && !rerouted.road_ids.includes(closingRoad) && rerouted.eta_min > first.eta_min,
    'Expected a longer real-road detour for the same vehicle and start');
  await resultRow(first.event_id).getByText('起点 ' + start + ' → 求救点 ' + target).waitFor();
  await resultRow(other.event_id).getByText('路网 v0 的结果已过期').waitFor();
  if (capture) {
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'output/playwright/cityrescue-b-after.png' });
  }

  const outgoing = campus.roads.filter((road) => road.from_node === start || (!road.one_way && road.to_node === start));
  for (const road of outgoing) {
    await select('路段').selectOption(road.road_id);
    await post(() => button('封闭道路').click(), '/roads/' + road.road_id + '/close');
  }
  const blocked = await post(() => button('重规划 ' + first.event_id).click(), '/dispatch/replan');
  verify(blocked.result.assignments[0].outcome === 'unreachable' && blocked.result.assignments[0].eta_min === null,
    'Expected unreachable after closing all outgoing sections');
  await page.getByRole('alert').getByText('当前路网不可达', { exact: false }).waitFor();
  for (const road of outgoing) {
    await select('路段').selectOption(road.road_id);
    await post(() => button('撤销人工封路').click(), '/roads/' + road.road_id + '/open');
  }
  await post(() => button('重规划 ' + first.event_id).click(), '/dispatch/replan');
  await resultRow(first.event_id).getByRole('button', { name: '标记完成' }).click();
  await taskRow(first.event_id).getByText('已完成', { exact: false }).waitFor();
  const released = await post(() => button('调度待处理任务').click(), '/dispatch');
  verify(released.result.assignments.length === 1 && released.result.assignments[0].vehicle_id === first.vehicle_id,
    'Only the completed task’s vehicle should be released');

  await select('灾害情景').selectOption('JL-EARTHQUAKE-01');
  await button('启动新情景').click();
  await button('保留当前情景').click();
  await taskRow(first.event_id).getByText('已完成', { exact: false }).waitFor();
  await button('启动新情景').click();
  const earthquake = await post(() => button('确认启动').click(), '/simulation/runs', 201);
  verify(earthquake.scenario_id === 'JL-EARTHQUAKE-01' && earthquake.run_id !== run.run_id,
    'Expected an independent earthquake run');
  await button('添加求救任务').click();
  await page.getByRole('checkbox', { name: '模拟车辆全部不可用' }).check();
  const unavailable = await post(() => button('调度待处理任务').click(), '/dispatch');
  verify(!unavailable.result.assignments.length && unavailable.result.unassigned_events.includes('B-E1'),
    'Expected no assigned vehicle in the unavailable scenario');

  const external = await page.request.post(path('/simulation/runs/' + earthquake.run_id + '/roads/' + closingRoad + '/close'),
    { data: { state_version: 0 } });
  verify(external.ok() && (await external.json()).changed, 'Expected a newer road state from another client');
  await post(() => button('调度待处理任务').click(), '/dispatch', 409);
  await page.getByRole('alert').getByText('检查最新状态后重试', { exact: false }).waitFor();
  await page.getByText('当前路网 v1', { exact: true }).waitFor();
  await page.getByRole('checkbox', { name: '模拟车辆全部不可用' }).uncheck();

  let accepted;
  await page.route(path('/dispatch'), async (route) => {
    accepted = await (await route.fetch()).json();
    await route.abort();
  }, { times: 1 });
  await button('调度待处理任务').click();
  await page.getByText('等待同步路网').waitFor();
  verify(accepted?.result.assignments.length === 1, 'Expected backend assignment before the lost response');
  await button('重新同步当前运行').click();
  await taskRow('B-E1').getByText('已分配', { exact: false }).waitFor();
  verify(await button('调度待处理任务').isDisabled(), 'Recovered assignment must not dispatch twice');

  await page.setViewportSize({ width: 320, height: 900 });
  verify(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Horizontal overflow at 320px');
  return { roads: campus.roads.length, vehicle: first.vehicle_id, event: first.event_id, closingRoad,
    before: first.eta_min, after: rerouted.eta_min };
}
