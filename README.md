# Canteen Monitor

Windows-first collection of public aggregate Wi-Fi BSS Load broadcasts.
Station Count means associated wireless terminals, **not people**.

## Setup

Requires Python 3.12+ and Windows Wi-Fi for live scans. Parser/database tests
also run without Wi-Fi. Configuration is in `config.toml`; paths resolve relative
to that file, not the current shell directory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

No fixed campus IP, credentials, or administrator access is required.
Do not collect client MAC addresses, traffic, or access unauthorized management
interfaces. Only AP BSSIDs and broadcast aggregate statistics belong here.

## Implemented Stages

1. Package structure, configuration, Python 3.12 virtual environment and tests.
2. Windows subprocess scanner with timeout, exit-code handling, raw stdout/stderr
   byte preservation and UTF-8/OEM/Chinese decoding.
3. English/Chinese BSS Load parser with multiple SSIDs/BSSIDs, null versus zero,
   explicit band information and separate raw/display utilization values.
4. SQLAlchemy/SQLite append-only observation history, scan sessions and AP registry;
   UTC timestamps, indexes, source/collector labels, filtering and online backup.
5. Serial periodic collection (default 60 seconds after each completed scan),
   failure logging and graceful Ctrl+C between scans. Basic manual exact-BSSID
   labeling is available; full geographical mapping remains a later phase.

Each stage is covered by automated tests. The Python suite currently has 35 tests.

## Dashboard (Approved B3 Design)

The local React + TypeScript + ECharts dashboard implements the approved sidebar
layout with warm ivory, charcoal and rust-orange colors. Real SQLite data is the
default. The clearly labeled demo switch generates in-memory example data only;
it never inserts simulated records into SQLite.

Implemented: overview, searchable/filterable AP list, per-BSSID station-count and
utilization trends, CSV export of the displayed history, read-only region mappings,
collector configuration, stale/failure/empty states, and mobile layout. The page
refreshes every 15 seconds while visible; this is separate from the 60-second
Wi-Fi collection interval. Auto-refresh can be disabled on the Settings page.

The UI never calls an AP count a count of physical access points: visible AP
metrics are explicitly counted by BSSID. Missing scan points remain null in charts.
History uses the selected AP's collector and a 2-hour, 24-hour or 7-day window,
limited to the latest 10,000 scan points per series with a visible truncation note.
The second series, when available, is another AP seen by the same collector.

Build and run (Node.js required for the build, not for the production server):

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m canteen_monitor serve --collect
```

Open `http://127.0.0.1:8000`. `serve --collect` runs the local API, frontend and
periodic scanner together. `serve` without `--collect` only reads existing data.
Do not also run a separate `collect` command with the same collector ID unless
duplicate scans are intentional. The server binds only to loopback, does not
publish campus data to the internet and does not install a Windows service.
It must remain running for collection to continue. Optional `--port 8001` changes
the server port. A standard source checkout is required for the frontend assets.

For frontend development, start the API on port 8000 and run `npm.cmd run dev`
in `frontend`; Vite proxies `/api` to the local backend.

Read-only endpoints:

- `GET /api/health`
- `GET /api/dashboard/summary`
- `GET /api/aps/{bssid}/history?collector_id=windows_01&hours=24`

Latest readings are selected per collector; identical BSSIDs from different
collectors are deduplicated using the latest timestamp. A failed latest scan
does not reuse old observations as current values. Existing observations from
stale successful scans remain visible but are labeled stale. Registry entries
remain available even when an AP is absent from the current scan.

Dashboard tests (with the local server running on port 8000 and Edge installed):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run test:e2e
```

The browser suite exercises mode switching, search/filtering, history export,
navigation, empty/error states and 1024/768/390px layouts. Screenshots are saved
in `docs/screenshots`; the `demo` filenames show explicitly simulated UI data.
These are browser screenshots, not the generated design concepts.

## Layout

```text
config.toml
pyproject.toml
requirements.txt
src/canteen_monitor/
  config.py       configuration validation
  models.py       validated, collector-independent observation schema
  scanner.py      netsh process and byte decoding
  parser.py       bilingual field parser
  storage.py      database schema, transactions, history and backup
  collector.py    one-shot and periodic orchestration
  cli.py          command line entry point
tests/
  fixtures/       synthetic English and Chinese samples
  test_*.py
data/             local database and backups, ignored by Git
```

## Run

After setup, run these commands from the project root:

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor scan
.\.venv\Scripts\python.exe -m canteen_monitor collect
```

`scan` returns exit code 1 on failure. `collect` logs failures and retries at the
next interval. It does not install a service or run silently in the background.
The interval, timeout, collector ID and optional scan vantage label are configurable
in `config.toml`. Use `--config path\to\config.toml` before the subcommand for
another configuration. Different collectors should have distinct IDs.

Read the latest 100 matching observations (JSON with UTC timestamps):

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor history --bssid 02:00:00:00:00:02 --limit 100
.\.venv\Scripts\python.exe -m canteen_monitor history --ssid Campus-Demo --since "2026-11-19T00:00:00+08:00" --until "2026-11-20T00:00:00+08:00"
```

Time filters require an explicit timezone. History returns newest first, defaults
to 1,000 records and allows at most 10,000 per query. Shanghai is UTC+08:00;
the later dashboard must display Asia/Shanghai rather than treating UTC as local.

Manually label an **already observed** BSSID (example only, not an inferred claim):

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor map aa:bb:cc:dd:ee:ff "candidate-area" --confidence 0.4 --notes "Observed nearby; installation not confirmed"
.\.venv\Scripts\python.exe -m canteen_monitor history --location "candidate-area"
```

Mapping is unconfirmed unless `--confirmed` is explicitly supplied. Confidence
is in [0, 1]. Mapping uses the exact BSSID, never a vendor prefix; later scans
do not overwrite manual labels. `--location` uses the current registry mapping,
not a claim about historical installation locations. The scan vantage label
is stored separately on each session. Historical dormitory/classroom fingerprints
from the brief are not pre-seeded as confirmed physical AP locations.

Create a consistent SQLite backup, including committed WAL data:

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor backup data/backups/manual.sqlite3
```

The destination must not already exist. Backup is verified in tests by opening
the resulting database, checking SQLite integrity and checking record counts.

## Data Semantics

- `station_count = null` means missing; `0` means explicitly broadcast zero.
- An absent AP is not inserted with a zero count.
- `channel_utilization_raw` retains only an explicit 0..255 raw value.
  Computed percentage is `raw / 255 * 100`; rounded netsh percentages are kept
  separately as `channel_utilization_display_percent`. A percent-only field
  leaves the raw value null; no raw value is reverse-engineered.
- No assumption is made about the band when Windows omits it. AP BSSIDs are
  not automatically merged, even for the same SSID, prefix or physical device.
- All scan output is retained as bytes in `scan_sessions`, including failed
  commands. Decoded stdout is also saved when decoding succeeds. Explicit
  zero-network results succeed with no observations; unrecognized output fails.
- Parsing or validation failures reject the entire scan's observations rather
  than inserting a misleading partial result. Their raw session remains saved.
- Observations, registry refresh and session completion commit transactionally.
  New scans append rows. A finalized session cannot be finalized again.
- A killed process or storage failure may leave a `running` session. This is
  incomplete, not successful; restarting never fabricates observations for it.
- Windows may return cached scan results. The timestamp records command execution,
  not a guaranteed beacon measurement time. This command does not force an active
  fresh scan. Nearby coverage and roaming can change the observed AP set.

If netsh fails because the Wi-Fi radio, driver, WLAN service or Windows location
permission is unavailable, the failure is recorded. The collector does not
change operating-system permissions, attempt administrator access or fake data.

## Verification And Limits

Both English and Chinese fixtures use fictional AP identifiers and synthetic
measurements. They are parser tests, not live captures or occupancy evidence.
Synthetic data is never imported into the production database.

## Deferred Scope

Authenticated HTTP ingestion, write APIs, CSV mapping import/export,
fingerprint rankings, canteen/manual occupancy tables
and trained occupancy/forecast models are **not implemented**. Region mappings and
configuration are read-only in the browser; existing CLI mapping is retained.
No device sum is exposed as a people estimate.
Schema migration tooling will be needed before future incompatible DB changes.
The current schema creates only the three collection-stage tables. Core parser,
schema and storage are independent of HTTP or frontend code for later expansion.
