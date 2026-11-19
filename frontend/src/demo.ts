import type { Summary, Point } from './types';
export function demoSummary(): Summary {
  const timestamp = new Date().toISOString();
  const ids = ['02:00:00:00:00:01', '02:00:00:00:00:02', '02:00:00:00:00:03', '02:00:00:00:00:04', '02:00:00:00:00:05', '02:00:00:00:00:06'];
  const aps = ids.map((bssid, i) => ({ bssid, ssid: i === 5 ? 'Campus-Demo-Secure' : 'Campus-Demo', band: i === 2 ? '2.4GHz' : '5GHz', channel: [36,52,11,52,36,60][i], signal: [65,91,38,14,60,20][i], station_count: [7,4,0,9,6,null][i], channel_utilization_percent: [5.9,3.9,2,9.8,6.7,null][i], collector_id: 'demo_01', timestamp, location_name: null, confirmed: 0, confidence: null }));
  return { timestamp, aps, registry: aps.map(a => ({...a, last_seen:timestamp})), collectors: [{id:1,timestamp,collector_id:'demo_01',status:'success',fresh:true,error:null,scan_location:'示例采样点'}], interval_seconds:60,timeout_seconds:30,collector_id:'demo_01',collection_enabled:false };
}
export function demoPoints(count: number | null): Point[] {
  const values = [3,4,4,5,6,8,6,7,7];
  return values.map((value, i) => {
    const station_count=count===null?null:Math.round(value*count/7);
    return {timestamp: new Date(Date.now() - (8-i)*15*60000).toISOString(), station_count,channel_utilization_raw:station_count===null?null:station_count*2};
  });
}
