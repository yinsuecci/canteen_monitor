import { test, expect } from '@playwright/test';

test('real data, demo switch, filters, chart and navigation', async ({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'监测总览'})).toBeVisible();
  await expect(page.getByRole('button',{name:'真实数据'})).toBeVisible();
  for (const removed of ['校园 Wi-Fi 监测','每一次扫描，都有迹可循。','WIRELESS OBSERVATORY','含明确的零值','按 BSSID 去重','不将终端数直接换算为人数','关联终端数不等于实际人数','只读监测 · v0.1']) {
    await expect(page.getByText(removed,{exact:true})).toHaveCount(0);
  }
  await expect(page.locator('.metric-sub')).toHaveCount(0);
  await expect(page.locator('footer')).toHaveCount(0);
  await expect(page.locator('.metric-value').first()).not.toHaveText('加载中');
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'../docs/screenshots/dashboard-real-desktop.png',fullPage:true,animations:'disabled'});
  await page.getByRole('button',{name:'真实数据'}).click();
  await expect(page.getByText('演示模式 · 所有数值与曲线均为示例，不写入数据库。')).toBeVisible();
  await expect(page.locator('canvas')).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(6);
  await page.getByRole('button',{name:'利用率',exact:true}).click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 CSV'}).click();
  expect((await download).suggestedFilename()).toBe('demo-history.csv');
  await page.getByRole('button',{name:'终端数',exact:true}).click();
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'../docs/screenshots/dashboard-demo-desktop.png',fullPage:true,animations:'disabled'});
  await page.getByRole('link',{name:'AP 管理',exact:true}).click();
  await page.getByRole('combobox', {name:'频段',exact:true}).selectOption('2.4GHz');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button',{name:'清除筛选'}).click();
  await page.getByRole('textbox',{name:'搜索 BSSID 或 SSID'}).fill('not-found');
  await expect(page.getByText('没有匹配的 AP')).toBeVisible();
  await page.getByRole('button',{name:'清除筛选'}).click();
  await page.getByRole('button',{name:'02:00:00:00:00:02',exact:true}).click();
  await expect(page.getByRole('heading',{name:'监测总览'})).toBeVisible();
  await page.getByRole('link',{name:'区域',exact:true}).click();
  await expect(page.getByRole('heading',{name:'人工映射'})).toBeVisible();
  await page.getByRole('link',{name:'设置',exact:true}).click();
  await page.getByRole('checkbox',{name:'自动刷新',exact:true}).uncheck();
  await expect(page.getByRole('checkbox',{name:'自动刷新',exact:true})).not.toBeChecked();
  expect(errors).toEqual([]);
});

test('responsive layout and mobile navigation',async({page})=>{
  for (const width of [1024,768,390]) {
    await page.setViewportSize({width,height:900});await page.goto('/');
    await page.getByRole('button',{name:'真实数据'}).click();
    await expect(page.locator('canvas')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if(width===390) await page.screenshot({path:'../docs/screenshots/dashboard-demo-mobile.png',fullPage:true});
  }
  await page.getByRole('link',{name:'AP 管理',exact:true}).click();
  await expect(page.getByRole('heading',{name:'AP 管理',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('connection failure and empty data are honest states',async({page})=>{
  await page.route('**/api/dashboard/summary',route=>route.abort());
  await page.goto('/');
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByText('无法读取数据。',{exact:false})).toBeVisible();
  await expect(page.locator('.metric-value').nth(1)).toHaveText('—');
  await page.unroute('**/api/dashboard/summary');
  await page.route('**/api/dashboard/summary',route=>route.fulfill({json:{timestamp:new Date().toISOString(),collectors:[],aps:[],registry:[],interval_seconds:60,timeout_seconds:30,collector_id:'test',collection_enabled:false}}));
  await page.getByRole('button',{name:'重试',exact:true}).click();
  await expect(page.getByText('暂无扫描数据')).toBeVisible();
  await expect(page.getByText('该时段暂无有效数据')).toBeVisible();
  await expect(page.locator('.metric-value').first()).toHaveText('待采集');
});

test('stale readings and explicit zero remain distinguishable',async({page})=>{
  const timestamp=new Date(Date.now()-86400000).toISOString();
  await page.route('**/api/dashboard/summary',route=>route.fulfill({json:{timestamp:new Date().toISOString(),collectors:[{id:1,timestamp,collector_id:'test',status:'success',fresh:false,error:null,scan_location:''}],aps:[{bssid:'aa:bb:cc:dd:ee:01',ssid:'test',band:'5GHz',channel:36,signal:50,station_count:0,channel_utilization_percent:null,collector_id:'test',timestamp,location_name:null,confirmed:0,confidence:null}],registry:[],interval_seconds:60,timeout_seconds:30,collector_id:'test',collection_enabled:false}}));
  await page.route('**/api/aps/**/history*',route=>route.fulfill({json:{points:[],truncated:false}}));
  await page.goto('/');
  await expect(page.getByText('采集数据已过期，以下为最后扫描记录。')).toBeVisible();
  await expect(page.locator('.station')).toHaveText('0');
  await expect(page.locator('tbody tr td').last()).toHaveText('—');
  await expect(page.locator('.metric-value').first()).toHaveText('已过期');
});

test('device onboarding, credential download, edits and rotation',async({page})=>{
  const device={collector_id:'test_probe',name:'食堂测试探针',location:'入口',source:'esp32_c5',interval_seconds:60,enabled:true,online:false,data_fresh:false,last_received_at:null,last_observed_at:null,last_status:null,last_error:null};
  let created=false;
  await page.route('**/api/devices',async route=>{
    if(route.request().method()==='POST'){
      expect(route.request().headers()['x-local-admin']).toBe('1');
      Object.assign(device,route.request().postDataJSON());created=true;
      await route.fulfill({status:201,json:{collector_id:device.collector_id,token:'test-only-not-a-real-key'}});
    }else await route.fulfill({json:created?[device]:[]});
  });
  await page.route('**/api/devices/test_probe',async route=>{Object.assign(device,route.request().postDataJSON());await route.fulfill({json:{updated:true}});});
  await page.route('**/api/devices/test_probe/rotate-key',route=>route.fulfill({json:{collector_id:'test_probe',token:'rotated-test-only-key'}}));
  await page.goto('/#devices');
  await expect(page.getByText('尚未连接采集设备')).toBeVisible();
  await page.getByRole('button',{name:'添加设备',exact:true}).click();
  await page.getByLabel('设备 ID',{exact:true}).fill('test_probe');
  await page.getByLabel('名称',{exact:true}).fill('食堂测试探针');
  await page.getByLabel('采样位置',{exact:true}).fill('入口');
  await page.getByRole('button',{name:'创建设备',exact:true}).click();
  await expect(page.getByText('test-only-not-a-real-key',{exact:true})).toBeVisible();
  const file=page.waitForEvent('download');await page.getByRole('button',{name:'下载凭据'}).click();
  expect((await file).suggestedFilename()).toBe('test_probe-credentials.json');
  await page.getByRole('button',{name:'关闭密钥'}).click();
  await expect(page.getByText('test-only-not-a-real-key',{exact:true})).toHaveCount(0);
  await expect(page.getByText('待接入',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'编辑',exact:true}).click();
  await page.getByLabel('采样位置',{exact:true}).fill('东门');
  await page.getByRole('button',{name:'保存',exact:true}).click();
  await expect(page.getByRole('cell',{name:'东门',exact:true})).toBeVisible();
  page.on('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'停用',exact:true}).click();
  await expect(page.getByText('已停用',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'重置密钥',exact:true}).click();
  await expect(page.getByText('rotated-test-only-key',{exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('real device page starts without fake devices',async({page})=>{
  await page.goto('/#devices');
  await expect(page.getByRole('heading',{name:'采集设备',exact:true}).first()).toBeVisible();
  await expect(page.getByText('尚未连接采集设备')).toBeVisible();
  await page.screenshot({path:'../docs/screenshots/devices-real-desktop.png',fullPage:true,animations:'disabled'});
});
