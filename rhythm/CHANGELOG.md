# 0.2.1-dev.2026112601 (prebuilt qualification pilot)

- Connect Home Assistant's Model Context Protocol integration to Rhythm by entering the browser's confirmation code in the owner's Rhythm app. The owner can decline the request or revoke the connection later in Assistant access.
- Review assistant proposals for saved lighting changes on the owner's phone.
- Update the packaged Rhythm server, admin API and Ingress web interface to Rhythm OS `v0.6.669-beta`. The published ARM64 and AMD64 images passed the container smoke checks and anonymous registry verification.

# 0.2.1-dev.2026111901 (prebuilt qualification pilot)

- Add Rhythm's assistant operations and an MCP endpoint on the app listener. An MCP client, such as Home Assistant's Model Context Protocol integration, can read lighting state, adjust rooms, run trials that can be undone, and propose saved changes.
- Assistant access stays off until an owner creates a credential in the Rhythm app. A saved change requested by an assistant waits for the owner's approval in the app.
- A trial is refused where its lights could not be restored. Undo reports whether the lights were restored, and a trial interrupted by a restart is restored afterwards.
- Publish the exact locally tested ARM64 and AMD64 images. ARM64 smoke checks ran natively and AMD64 checks ran under emulation. Full HAOS qualification remains pending, and the assistant operations have not yet been exercised with a live Assist conversation.

# 0.2.1-dev.2026111501 (prebuilt qualification pilot)

- Keep the Home Assistant command connection responsive during quiet periods so the next light action, including a motion shutoff or warning dim, can reach Home Assistant.
- Replace a stale connection before sending a light command. Commands with an uncertain result are sent at most once.

# 0.2.1-dev.2026110802 (prebuilt qualification pilot)

- Allow authenticated Identify requests through the Home Assistant app's API policy so they reach the native Identify controller.
- Preserve existing authentication and device ownership checks, and reject invalid Identify paths and methods.
- Publish the exact locally tested ARM64 and AMD64 images. ARM64 smoke checks ran natively and AMD64 checks ran under emulation; full HAOS qualification remains pending.

# 0.2.1-dev.2026110801 (prebuilt qualification pilot)

- Use Home Assistant's native Identify buttons for Matter lights, preserving light power and brightness.
- Retain native flash for lights that advertise it, and reject unsupported Identify actions without changing light output.
- Recheck reviewed light ownership and current identification controls before dispatch.
- Publish the exact locally tested ARM64 and AMD64 images. ARM64 smoke checks ran natively and AMD64 checks ran under emulation; full HAOS qualification remains pending.

# 0.2.1-dev.2026110501 (prebuilt qualification pilot)

- Support Home Assistant-owned Matter management and pairing recovery from the Rhythm mobile app.
- Transfer lighting settings from a Light Box backup with reviewed room and light mappings.
- Preserve resolved room schedule modes through realtime updates and correct daylight-saving clock transitions.
- Publish the exact locally tested ARM64 and AMD64 images. ARM64 smoke checks ran natively and AMD64 checks ran under emulation; real HAOS qualification remains pending.

# 0.2.1-dev.2026100404 (prebuilt qualification pilot)

- Show observed light power, brightness and color temperature separately from requested curve values in the admin interface.
- Preserve observed power when enabling or pausing Rhythm without sending a light command.
- Retain locally built, smoke-tested images for both architectures; Home Assistant pulls the prebuilt image.

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
