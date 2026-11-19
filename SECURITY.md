# Security Policy

This is an experimental local dashboard and authenticated collector receiver,
not a hardened public multi-tenant service. Only the latest main branch receives
security fixes. A passing test or vulnerability scan is not a security guarantee.

## Deployment Boundary

- Keep the dashboard on server localhost. Data reads and administration require
  a loopback peer and Host; cross-origin requests are rejected.
- Remote collectors may use only `/api/collector/observations`, authenticated by
  a unique per-device Bearer credential. `/api/health` is public and contains no
  network observations. Never expose other API routes through a reverse proxy:
  a loopback proxy would otherwise make a remote caller appear local.
- Use the CLI server, which disables forwarded-header trust. Do not enable
  `proxy_headers` in an alternate ASGI deployment.
- Use HTTPS for remote ingestion. Explicit insecure HTTP mode is for isolated
  testing only; it exposes device credentials and scan data in transit.
- At an ingestion gateway, enforce request size, connection/time limits and
  per-device rate limits. The application bounds each batch but does not enforce
  disk quotas, retention, or global upload rates. Do not expose it directly to
  the public Internet.
- Device credentials authorize data submission, not trustworthy measurements.
  An authorized compromised device can fabricate observations. Disable or rotate
  its credential immediately. Unknown/missing load values are not zero people.

## Data Handling

AP identifiers, SSIDs, locations, timestamps, raw scanner output and error text
may reveal deployment details. Store them only in private local databases with
appropriate OS access controls. Backups and upload queues require the same
protection. Do not commit databases, captures, credentials, screenshots showing
live data, or personally identifying paths. Git ignores are a guardrail, not a
substitute for reviewing staged changes. Examples must use fictional identifiers.

## Reporting

Do not post credentials, private captures, or identifying data in public issues.
Use GitHub private vulnerability reporting if available on this repository;
otherwise open a non-sensitive issue requesting a private reporting channel.
Private vulnerability reporting availability is not guaranteed by this file.

## Historical Data

History rewriting removes information from branch history, but does not revoke
copies, forks, cached views or unreachable GitHub objects. Old public commit
objects require separate GitHub-side cleanup. This project must not claim that
a force push alone erased previously published data.
