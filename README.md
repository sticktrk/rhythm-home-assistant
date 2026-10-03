# Rhythm for Home Assistant

Rhythm's lighting engine with Home Assistant-owned devices and two separate interfaces: the mobile app connects directly over LAN or the existing Rhythm tunnel, and the existing **admin API and web UI** run through Home Assistant Ingress. Flutter stays mobile-only and is not part of this image.

This repository owns install metadata, packaging and public build checks. Shared Rust, pure Dart and React source remain in [rhythm-os](https://github.com/sticktrk/rhythm-os), pinned by [source.lock.json](source.lock.json). Release publishing is operated separately; public CI cannot publish images.

**Experimental implementation, pending HAOS qualification.** Initial targets are amd64 and aarch64. After the packaging PR lands, installation builds from pinned source. Qualified prebuilt images will be advertised through a separate release.

## Use

See [installation, recovery and migration](rhythm/DOCS.md). Add this repository through the Home Assistant app/add-on store, install and start Rhythm, then open its Web UI as a HA administrator. Select managed lights, review profiles and enable adaptation. The admin interface needs no manually entered HA URL or token. To connect a compatible mobile app, generate an enrollment code in Mobile access and enter the HA host's LAN address and mapped mobile port. Remote access uses the existing Rhythm account and tunnel flow.

This repository has a different Supervisor installation identity from the legacy sticktrk/rhythm-os-addon. Stop the old controller before enabling the new one.

## Build and test

Requirements: Python 3, Docker with Buildx and access to public source/toolchain registries. No Flutter SDK is used.

    python3 tools/validate.py
    python3 -m unittest discover -s tools -p 'test_*.py'
    python3 tools/build.py --platform linux/arm64 --tag rhythm-ha:review
    python3 tools/smoke.py --image rhythm-ha:review

The harness tests the real image through a synthetic Supervisor. The fixture enforces the authenticated `/core/api/` REST and `/core/websocket` upgrade paths, so incorrect proxy URLs cannot pass as a working installation. It needs the 172.30.32.0/24 Docker subnet to be unused and fails on collision. Do not run it on the production HA host. Test containers and data are removed afterward.

Build both architectures into a local artifact:

    python3 tools/build.py --platform linux/amd64,linux/arm64 --output candidate.oci.tar

Product SHA updates change both Dockerfile arguments and the source lock together. Record native architecture checks and qualify actual HAOS behavior before release.

## Container boundary

Ingress:8099 → Nginx → local admin API:8787 → admin-only Rhythm:54449 → Supervisor → HA Core

Mobile LAN/mapped port or outbound tunnel → authenticated Rhythm:54448 → Supervisor → HA Core

Nginx accepts Ingress exclusively from Supervisor; the admin API separately verifies active HA administrator status. The mobile listener always requires a durable phone bearer for control and ignores Ingress identity headers. Single-use enrollment codes can only be created through authorized administration. Browser responses receive neither service token. Persistent state lives in /data/rhythm; the separate ephemeral admin token lives in /run/rhythm.

Only the mobile port is published. No host networking, privileged devices, host configuration mounts, Docker socket, Supervisor management API or password-validation API is requested. A pinned cloudflared binary provides the existing outbound tunnel.

Licensed under Apache-2.0.
