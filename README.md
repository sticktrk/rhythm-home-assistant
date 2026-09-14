# Rhythm for Home Assistant

Rhythm's existing **admin API and web UI**, embedded through Home Assistant Ingress with an automatic local HA connection. Flutter stays mobile-only and is not part of this image.

This repository owns install metadata, packaging and public build checks. Shared Rust, pure Dart and React source remain in [rhythm-os](https://github.com/sticktrk/rhythm-os), pinned by [source.lock.json](source.lock.json). Release publishing is operated separately; public CI cannot publish images.

**Experimental implementation, pending HAOS qualification.** Initial targets are amd64 and aarch64. After the packaging PR lands, installation builds from pinned source. Qualified prebuilt images will be advertised through a separate release.

## Use

See [installation, recovery and migration](rhythm/DOCS.md). Add this repository through the Home Assistant app/add-on store, install and start Rhythm, then open its Web UI as a HA administrator. Select managed lights, review profiles and enable adaptation. No URL, token, external hub or Rhythm cloud login is required.

This repository has a different Supervisor installation identity from the legacy sticktrk/rhythm-os-addon. Stop the old controller before enabling the new one.

## Build and test

Requirements: Python 3, Docker with Buildx and access to public source/toolchain registries. No Flutter SDK is used.

    python3 tools/validate.py
    python3 -m unittest discover -s tools -p 'test_*.py'
    python3 tools/build.py --platform linux/arm64 --tag rhythm-ha:review
    python3 tools/smoke.py --image rhythm-ha:review

The harness tests the real image through a synthetic Supervisor. It needs the 172.30.32.0/24 Docker subnet to be unused and fails on collision. Do not run it on the production HA host. Test containers and data are removed afterward.

Build both architectures into a local artifact:

    python3 tools/build.py --platform linux/amd64,linux/arm64 --output candidate.oci.tar

Product SHA updates change both Dockerfile arguments and the source lock together. Record native architecture checks and qualify actual HAOS behavior before release.

## Container boundary

Ingress:8099 → Nginx → local admin API:8787 → Rhythm:54448 → Supervisor → HA Core

Only Nginx listens outside loopback; it accepts Ingress exclusively from Supervisor. The API separately verifies active HA administrator status. Browser assets/responses receive neither service token. State lives in /data/rhythm; the ephemeral token lives in /run/rhythm.

No host networking, published ports, privileged devices, host configuration mounts, Docker socket, Supervisor management API or password-validation API is requested.

Licensed under Apache-2.0.
