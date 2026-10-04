# 0.2.1-dev.2026100402 (development candidate)

Support authenticated mobile access over IPv4 and IPv6 on Home Assistant's dual-stack container network. Extend real-image smoke coverage to IPv6 health, enrollment, bearer access, restart continuity and revocation while keeping the administrator listener private.

Prepare locally built, smoke-tested multi-architecture image artifacts with immutable source, packaging and image receipts. Verify both images are publicly accessible before advertising their version to Home Assistant. Keep the catalog at `0.2.0` until the first image is published and verified, so existing installations are not offered another source-build update. After promotion, retain the last published catalog version while preparing newer local candidates.

# 0.2.0 (experimental; pending qualification)

Add authenticated direct mobile access on mapped port 54448, single-use enrollment through Ingress, durable phone credentials, and the existing outbound Rhythm tunnel using pinned cloudflared. Keep the internal administrator listener separate. Require reviewed stable HA light identities and current inventory for selection. Extend real-image smoke checks for listener isolation, enrollment, restart continuity, revocation and selection conflicts.

Real HAOS, both native architectures, phone LAN/cellular, hardware migration and rollback qualification remain required before release. Legacy runtime retirement is gated on those checks.

# 0.1.0 (experimental)

Initial local admin web UI, automatic Supervisor connection, explicit managed light selection, and Home Assistant lifecycle packaging. Release qualification is tracked in the pull request; no stable image is advertised yet.
