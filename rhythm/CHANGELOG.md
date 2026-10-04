# 0.2.1-dev.2026100403 (prebuilt qualification pilot)

- Preserve per-light manual overrides with current and legacy HA integration identifiers, including a single selected light in an area.
- Expose immutable image provenance in health and administration status, verified against image labels by container smoke tests.
- Bound connector logs and restart backoff; prevent inherited output pipes from blocking connector recovery.
- Pin build image digests and Dart archive checksums. Both architectures are built and tested locally before publication.

# 0.2.1-dev.2026100402 (prebuilt qualification pilot)

Support authenticated mobile access over IPv4 and IPv6 on Home Assistant's dual-stack container network. Extend real-image smoke coverage to IPv6 health, enrollment, bearer access, restart continuity and revocation while keeping the administrator listener private.

Preserve individual HA light manual pauses and scoped actions when lights share an area.

Install the exact locally built, smoke-tested multi-architecture image. Both architectures are publicly accessible and their digests and provenance have been verified. Updating from `0.2.0` downloads the prebuilt image without compiling on the HA host. Keep the last published catalog version while preparing newer local candidates. Full HAOS, native AMD64 and physical-device qualification remain pending.

# 0.2.0 (experimental; pending qualification)

Add authenticated direct mobile access on mapped port 54448, single-use enrollment through Ingress, durable phone credentials, and the existing outbound Rhythm tunnel using pinned cloudflared. Keep the internal administrator listener separate. Require reviewed stable HA light identities and current inventory for selection. Extend real-image smoke checks for listener isolation, enrollment, restart continuity, revocation and selection conflicts.

Real HAOS, both native architectures, phone LAN/cellular, hardware migration and rollback qualification remain required before release. Legacy runtime retirement is gated on those checks.

# 0.1.0 (experimental)

Initial local admin web UI, automatic Supervisor connection, explicit managed light selection, and Home Assistant lifecycle packaging. Release qualification is tracked in the pull request; no stable image is advertised yet.
