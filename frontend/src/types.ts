export type AP = { bssid: string; ssid: string; band: string | null; channel: number | null; signal: number | null; station_count: number | null; channel_utilization_percent: number | null; collector_id: string; timestamp: string; location_name: string | null; confirmed: number; confidence: number | null };
export type Collector = { id: number; timestamp: string; collector_id: string; status: string; fresh: boolean; error: string | null; scan_location: string };
export type Registry = { bssid: string; location_name: string | null; confirmed: number; confidence: number | null; ssid: string; last_seen: string };
export type Summary = { timestamp: string; collectors: Collector[]; aps: AP[]; registry: Registry[]; interval_seconds: number; collector_id: string; timeout_seconds: number; collection_enabled: boolean };
export type Point = { timestamp: string; station_count: number | null; channel_utilization_raw: number | null };
export type Series = { name: string; points: Point[]; truncated?: boolean };
