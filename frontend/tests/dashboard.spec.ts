import { test, expect } from '@playwright/test';

test('real data, demo switch, filters, chart and navigation', async ({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'监测总览'})).toBeVisible();
  await expect(page.getByRole('button',{name:'真实数据'})).toBeVisible();
  await expect(page.locator('.metric-value').first()).not.toHaveText('加载中');
  await page.screenshot({path:'../docs/screenshots/dashboard-real-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'真实数据'}).click();
  await expect(page.getByText('演示模式 · 所有数值与曲线均为示例，不写入数据库。')).toBeVisible();
  await expect(page.locator('canvas')).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(6);
  await page.getByRole('button',{name:'利用率',exact:true}).click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 CSV'}).click();
  expect((await download).suggestedFilename()).toBe('demo-history.csv');
  await page.getByRole('button',{name:'终端数',exact:true}).click();
  await page.screenshot({path:'../docs/screenshots/dashboard-demo-desktop.png',fullPage:true});
  await page.getByRole('link',{name:'AP 管理',exact:true}).click();
  await page.getByLabel('频段', {exact:true}).selectOption('2.4GHz');
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
  await page.getByRole('checkbox').uncheck();
  await expect(page.getByRole('checkbox')).not.toBeChecked();
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
