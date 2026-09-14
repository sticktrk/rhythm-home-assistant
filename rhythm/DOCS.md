# Using Rhythm

This experimental add-on targets Supervisor installations, normally HAOS. Home Assistant Container does not provide add-ons. Real HAOS qualification and a minimum supported release are still pending; the synthetic container tests do not establish production readiness.

## Installation and first run

After the packaging PR is merged, add https://github.com/sticktrk/rhythm-home-assistant in the HA app/add-on store and install Rhythm. The first version builds pinned public source; a qualified prebuilt image will be added separately.

Start Rhythm and use **Open Web UI** or its sidebar entry from a Home Assistant administrator session. The interface uses the existing admin API and web UI; Flutter remains mobile-only. The HA connection is automatic and requires no URL, token, external bridge, Rhythm account or mobile onboarding.

1. Open **Managed lights** and select individual HA entities.
2. Save the selection; Rhythm stays paused.
3. Review rooms, profiles, scenes, modes and inputs.
4. Enable Rhythm from **Overview**.

New lights are excluded even when added to an existing area. Commands target exact selected entities. Review the selection after entity renames, and deselect an old entity before replacing hardware under the same entity ID. Avoid conflicting lighting automations on selected lights.

## Configuration and operation

The only add-on option is log_level: error, warn, info (default), or debug. No credential belongs in options.

Manage integrations, devices, areas, home location and timezone in Home Assistant. Rhythm imports them on connect and synchronization. Use **Home Assistant → Synchronize now** after changes made while connected. Automatic registry/config event reconciliation beyond existing reconnect behavior is planned.

The UI provides overview, managed selection, rooms/lights, profiles, scenes, modes, inputs, activity, connection status and system controls. It has no staff login/customer directory, external hub picker, pairing, remote tunnel, appliance updater or Flutter assets. The API also rejects those operations.

Regular or inactive HA users cannot use this interface. Sidebar restriction is supplemented by backend authorization; writes recheck the active administrator role immediately. Read authorization is cached for at most 15 seconds. If identity verification is unavailable, access fails closed.

## Persistence and recovery

Supervisor owns start, stop, updates and backups. Persistent state lives in /data/rhythm. Supervisor owns /data/options.json. Restart regenerates the internal API token and obtains the current Supervisor credential; the saved HA connection contains only a credential-source marker.

Take a Home Assistant cold backup before upgrading. Rollback restores the matching old image and data snapshot together. An image downgrade alone is not a safe schema rollback. The add-on has no runtime updater.

**System → Export profiles** transfers only the portable profile bundle. Restore pauses adaptation and does not import credentials, integrations or managed-light selection. Full configuration uses HA backups of this installation.

**Reset Rhythm** removes settings and selection and restarts the service. Home Assistant devices, integrations, options and other add-ons remain intact.

Core outages retain configuration while the runtime retries the connection. The API does not retry dispatched writes after an uncertain response. Reload before retrying a change.

## Legacy migration

The legacy sticktrk/rhythm-os-addon repository has a different Supervisor identity and separate data volume. Adding this repository is not an in-place upgrade.

Back up the old installation, stop its controller and install the new add-on. Recreate settings or transfer compatible portable profiles through a reviewed conversion. Legacy full-device backups are rejected because they may restore external credentials and appliance state. A migration preview/converter is planned. Do not blindly copy the old data directory or enable both controllers on the same lights.

## Diagnostics and qualification

For connection problems, confirm HA Core is running and synchronize. For an unchanged light, check managed selection, pause state, node preferences and HA availability. For access problems, reopen from an active administrator session.

Download bounded connection status from **System** and inspect Supervisor logs locally. Review logs before sharing because existing device logs may contain local entity names. No cloud account or analytics connection is provisioned.

Public tests cover the real image with a simulated Supervisor: startup, nested Ingress HTML, trusted identity, revocation, CSRF, forbidden routes, selection conflicts, persistence and token rotation. Real HAOS semantics, theme alignment, backup/restore, hardware behavior, upgrade/rollback and resource budgets remain release gates. Native checks are required on amd64 and aarch64.

References: [communication](https://developers.home-assistant.io/docs/apps/communication/), [Ingress](https://developers.home-assistant.io/docs/apps/presentation/), [security](https://developers.home-assistant.io/docs/apps/security/), [configuration](https://developers.home-assistant.io/docs/apps/configuration/).
