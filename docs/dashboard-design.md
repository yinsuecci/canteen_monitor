# Approved Dashboard Direction

User approved proposal B3: proposal A layout, proposal B palette, concise Chinese text.

- Fixed desktop sidebar, four metrics, large trend chart, compact status/region panels,
  AP table, disabled occupancy state. Stack panels and use top navigation on mobile.
- Warm ivory #f6f3ed, near-white #fffdf9, charcoal #302e29, rust #b64a20,
  muted olive #707c36, fine warm-gray borders. No gradients or decorative images.
- Serif wordmark and page title; clean Chinese UI typography; monospace BSSIDs.
- Small entrance transition; reduced-motion respected. Visible keyboard focus.
- Real data by default; explicit separate in-memory demo mode. Never infer people
  counts, AP installation location, or zero from missing observations.
- Local-only deployment: this dashboard reads the Windows collector's SQLite DB.
  No cloud publication or upload of campus scan data.
