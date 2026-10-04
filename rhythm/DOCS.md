# Using Rhythm

This experimental add-on targets Supervisor installations, normally HAOS. Home Assistant Container does not provide add-ons. Real HAOS qualification and a minimum supported release are still pending; the synthetic container tests do not establish production readiness.

## Installation and first run

For the current pre-merge qualification pilot, add `https://github.com/sticktrk/rhythm-home-assistant#codex/mobile-ha-platform` in the HA app/add-on store. Keep an existing pilot installation attached to that same repository. The catalog advertises `0.2.1-dev.2026100402` and downloads its published prebuilt image for your host architecture. Both a fresh installation and an update from `0.2.0` use the image without compiling software on Home Assistant. This pilot is still undergoing HAOS qualification.

Build future candidates locally and verify anonymous registry access before advancing the catalog. The repository README describes the exact-artifact workflow; development source builds remain available through `tools/build.py`.

Start Rhythm and use **Open Web UI** or its sidebar entry from a Home Assistant administrator session. The interface uses the existing admin API and web UI; Flutter remains mobile-only. The HA connection is automatic and requires no URL, token, external bridge, Rhythm account or mobile onboarding.

1. Open **Managed lights** and select individual HA entities.
2. Save the selection; Rhythm stays paused.
3. Review rooms, profiles, scenes, modes and inputs.
4. Enable Rhythm from **Overview**.

New lights are excluded even when added to an existing area. Commands target exact selected entities. Selection records registry identity independently of routing names. Replacements and unresolved identities require fresh review; stale catalog revisions cannot be saved. Avoid conflicting lighting automations on selected lights.

## Configuration and operation

The only add-on option is log_level: error, warn, info (default), or debug. No credential belongs in options.

Manage integrations, devices, areas, home location and timezone in Home Assistant. Rhythm imports them on connect and synchronization. Use **Home Assistant → Synchronize now** after changes made while connected. Registry/config events invalidate the catalog and trigger a complete refresh. Failed partial refreshes do not authorize new writes.

The UI provides overview, managed selection, rooms/lights, profiles, scenes, modes, inputs, activity, connection status and system controls. It has no staff login/customer directory, physical pairing, appliance updater or Flutter assets. Phones connect directly to a separate authenticated Rhythm API on mapped container port 54448; the existing Rhythm tunnel connects to that same internal port. The admin upstream stays on loopback port 54449.

Regular or inactive HA users cannot use this interface. Sidebar restriction is supplemented by backend authorization; writes recheck the active administrator role immediately. Read authorization is cached for at most 15 seconds. If identity verification is unavailable, access fails closed.

## Persistence and recovery

Supervisor owns start, stop, updates and backups. Persistent state lives in /data/rhythm. Supervisor owns /data/options.json. Restart preserves phone credentials, durable server identity and tunnel settings while regenerating the separate internal API token and obtaining the current Supervisor credential; the saved HA connection contains only a credential-source marker.

Take a Home Assistant cold backup before upgrading. Rollback restores the matching old image and data snapshot together. An image downgrade alone is not a safe schema rollback. The add-on has no runtime updater.

**System → Export profiles** transfers only the portable profile bundle. Restore pauses adaptation and does not import credentials, integrations or managed-light selection. Full configuration uses HA backups of this installation.

**Reset Rhythm** removes settings and selection and restarts the service. Home Assistant devices, integrations, options and other add-ons remain intact.

Core outages retain configuration while the runtime retries the connection. The API does not retry dispatched writes after an uncertain response. Reload before retrying a change.

## Legacy migration

The legacy sticktrk/rhythm-os-addon repository has a different Supervisor identity and separate data volume. Adding this repository is not an in-place upgrade.

Back up the old installation, stop its controller and install the new add-on. Recreate settings or transfer compatible portable profiles through a reviewed conversion. Legacy full-device backups are rejected because they may restore external credentials and appliance state. The product provides an offline `ha-migration-preview` example: it creates a reviewed portable-profile conversion and a device-candidate inventory without importing credentials or enabling writers. Follow the product migration contract for invocation and remaining manual mappings. Do not blindly copy the old data directory or enable both controllers on the same lights.

## Diagnostics and qualification

For connection problems, confirm HA Core is running and synchronize. For an unchanged light, check managed selection, pause state, node preferences and HA availability. For access problems, reopen from an active administrator session.

Download bounded connection status from **System** and inspect Supervisor logs locally. Review logs before sharing because existing device logs may contain local entity names. No cloud account or analytics connection is provisioned.

Public tests cover the real image with a simulated Supervisor: startup, nested Ingress HTML, trusted identity, revocation, CSRF, forbidden routes, selection conflicts, persistence and token rotation. Real HAOS semantics, theme alignment, backup/restore, hardware behavior, upgrade/rollback and resource budgets remain release gates. Native checks are required on amd64 and aarch64.

References: [communication](https://developers.home-assistant.io/docs/apps/communication/), [Ingress](https://developers.home-assistant.io/docs/apps/presentation/), [security](https://developers.home-assistant.io/docs/apps/security/), [configuration](https://developers.home-assistant.io/docs/apps/configuration/).

## Connect the mobile app

Open **Connect mobile app** as an HA administrator and generate a connection code.
In the Rhythm mobile app, add the HA host LAN address and the port in the add-on's
Network settings (default 54448), then paste the code. A code works once for five
minutes. Each phone receives a durable token; revoke it in the same admin page.
The Ingress URL is not the phone's API endpoint. Do not expose the LAN HTTP port
directly to the internet; configure existing Rhythm Remote Access in the app for
TLS tunnel access. Changing the mapped host port requires updating the phone's
LAN endpoint, while the tunnel origin remains localhost:54448.

Container cloudflared is pinned to release 2026.9.3 with architecture-specific
SHA-256 verification. It needs outbound connectivity, without Bluetooth, USB,
host D-Bus, host networking or Docker socket access. Full installation recovery
uses HA cold backups. A replacement-host restore requires stopping/revoking the
previous connector and reconciling ownership before enabling it; duplicate
installation prevention is a release qualification gate.
