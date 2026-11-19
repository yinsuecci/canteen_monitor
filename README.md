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

Each stage is covered by automated tests. The suite currently has 30 tests.

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

FastAPI/authenticated HTTP ingestion, React/ECharts dashboard/history curves,
CSV mapping import/export, fingerprint rankings, canteen/manual occupancy tables
and trained occupancy/forecast models are **not implemented**. Browser acceptance
criteria therefore remain open. No device sum is exposed as a people estimate.
Schema migration tooling will be needed before future incompatible DB changes.
The current schema creates only the three collection-stage tables. Core parser,
schema and storage are independent of HTTP or frontend code for later expansion.
