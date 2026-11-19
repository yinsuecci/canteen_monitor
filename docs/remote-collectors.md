# Remote Collectors (Protocol v1)

## Deployment

The dashboard server does not collect Wi-Fi by default. Run `python -m
canteen_monitor serve --host 0.0.0.0` to listen on a private network. The `--collect`
flag is retained only for explicit Windows debugging. Do not use it in a remote-only
deployment. Current UI hides local historical sessions by default; Settings has
a separate switch to view them without restarting scans.

Device management is at `/#devices`. Add a device to issue a random 256-bit token.
The secret is returned once, kept only in browser component memory, and stored
as a SHA-256 hash on the server. Downloaded credentials contain the plaintext key.
Keep them off Git. Rotation immediately invalidates the old key. Disabling a
device rejects uploads but retains history. IDs cannot reuse historical collector IDs.

Administrative mutations require a loopback TCP client, loopback Host, matching
Origin (when supplied), and `X-Local-Admin: 1`. No CORS permission is granted.
The built-in server disables proxy-header trust. For remote administration use a
trusted SSH tunnel to the server loopback UI, not forwarded client IP headers.
The ingestion interface authenticates devices independently with Bearer tokens.

All dashboard data reads also require a loopback peer, loopback Host and matching
Origin when supplied. Do not proxy read or administration routes to remote users:
a loopback reverse proxy can make them appear local. A collector gateway must
forward only `/api/collector/observations`, use HTTPS, and enforce request size,
timeouts and rate limits. There is no remote dashboard login in this version.
Do not expose the plain HTTP service to the internet. TLS certificates, public
DNS, firewall rules and campus network isolation are environment-specific and
have not been configured by this change.

The device must use the reachable server address, never its own `127.0.0.1`.
Campus client isolation may prevent direct device-to-computer connections even
when both devices use the same SSID. No inbound firewall bypass is attempted.

## Upload Contract

`POST /api/collector/observations`

Headers: `Content-Type: application/json`, `Authorization: Bearer <device token>`.
One request is one complete scan. Maximum 256 KiB and 512 AP readings. Only AP
BSSIDs are accepted; unknown fields (including client MAC fields) are rejected.

```json
{
  "schema_version": 1,
  "batch_id": "18a1535c-d2ae-43ce-b15d-1c4f3a55c8a2",
  "collector_id": "canteen_probe_01",
  "timestamp": "2026-11-19T14:00:00Z",
  "status": "success",
  "observations": [
    {
      "ssid": "Campus-Demo",
      "bssid": "aa:bb:cc:dd:ee:01",
      "band": "5GHz",
      "channel": 36,
      "rssi_dbm": -65,
      "station_count": 0,
      "channel_utilization_raw": 15,
      "available_admission_capacity": 30000
    }
  ]
}
```

This is a protocol example, not real sensor data. Optional fields are null when
unknown. `signal` is Windows percentage; `rssi_dbm` is a separate measurement,
never a percentage. Device type/source and scan vantage location come from the
registered device, not caller claims. Location does not automatically map APs.

An empty successful scan uses `observations: []`. A failed scan uses
`status: "failed"`, a nonempty `error`, and `observations: []`. No fake zero rows
are inserted for absent APs. Raw radio frames are not uploaded or retained by this
protocol; local Windows scanner raw-output retention is unchanged.

Generate a new UUID batch_id **once per scan**, then keep the exact same batch
through every retry. A repeated identical batch returns HTTP 200 with
`accepted: true, duplicate: true`; it does not append observations. Reusing the
ID for different content returns 409. Authentication failures return 401,
invalid fields 422, and oversized bodies 413. Batch inserts are atomic and
concurrent retries are serialized with SQLite BEGIN IMMEDIATE.

Use a timezone-aware acquisition timestamp. Future clocks beyond five minutes
are rejected. Old data is accepted for backfill, but never replaces newer scan
state or registry metadata. The server stores received_at separately. Device
connection is considered online for max(180 seconds, 3 x expected interval)
after an accepted upload, even if that upload contains stale data; acquisition
freshness is displayed separately. No upload means pending, not online. Scanner
failure is distinct from network disconnection.

## Durable Upload Client

`src/canteen_monitor/uploader.py` provides a SQLite-backed queue and HTTPS
uploading. Run it **on the independent collector**, not the dashboard computer.
Configuration template: `collector-config.example.toml`. Device secret is read
from the environment variable named by `token_env`; never put secrets on argv.

```powershell
python -m canteen_monitor.uploader --config collector-config.local.toml
```

This continuous mode is a Windows/netsh adapter. It is not ESP32 firmware.
`--once` performs one attempt; `--flush-only` uploads queued scans without
scanning. Other collectors can produce a protocol-v1 JSON file and use:

```powershell
python -m canteen_monitor.uploader --config collector-config.local.toml --enqueue scan.json
```

The queue is committed before upload. Failed, rejected or unacknowledged batches
remain after restart. Only an accepted acknowledgement removes an item. A lost
response is safe to retry because the server deduplicates. Retry delays back off
to five minutes in continuous mode; scanning follows that loop during outages.
At most 100 queued batches are sent per attempt. The oldest failing item blocks
later items; configuration/schema errors require correction rather than silently
discarding data. The queue is not capped and needs sufficient disk space.
HTTP is rejected unless allow_insecure_http=true is explicitly set for a trusted
private-network test. TLS validation is enabled; redirects are not followed.

## Hardware Boundary

The receiving service, device management, protocol and durable Python uploader
are implemented and tested. ESP32-C5 BSS Load parsing firmware, flash storage
queue, Wi-Fi onboarding and physical channel coverage tests are **not implemented
or validated here**. Registering a C5 does not make it send data automatically.
No physical C5 was connected, so actual hardware-to-server verification is still
pending. No simulated remote readings have been inserted into the production DB.
