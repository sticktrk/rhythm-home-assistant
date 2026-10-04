# Rhythm for Home Assistant

Rhythm's lighting engine with Home Assistant-owned devices and two separate interfaces: the mobile app connects directly over LAN or the existing Rhythm tunnel, and the existing **admin API and web UI** run through Home Assistant Ingress. Flutter stays mobile-only and is not part of this image.

This repository owns install metadata, packaging and public build checks. Shared Rust, pure Dart and React source remain in [rhythm-os](https://github.com/sticktrk/rhythm-os), pinned by [source.lock.json](source.lock.json). Release publishing is operated separately; public CI cannot publish images.

**Experimental implementation, pending HAOS qualification.** Initial targets are amd64 and aarch64. Production installs download a prebuilt multi-architecture image: no Rust, Dart or web compilation runs on the Home Assistant host. The current development manifest deliberately has no `image` key until a candidate has been published and verified. Its catalog stays at the earlier `0.2.0` development version while local candidates advance, so an existing `0.2.0` installation is not offered a source-build update. A fresh installation of this development branch would still build source on the host; wait for prebuilt promotion before installing it.

## Use

See [installation, recovery and migration](rhythm/DOCS.md). Add this repository through the Home Assistant app/add-on store, install and start Rhythm, then open its Web UI as a HA administrator. Select managed lights, review profiles and enable adaptation. The admin interface needs no manually entered HA URL or token. To connect a compatible mobile app, generate an enrollment code in Mobile access and enter the HA host's LAN address and mapped mobile port. Remote access uses the existing Rhythm account and tunnel flow.

This repository has a different Supervisor installation identity from the legacy sticktrk/rhythm-os-addon. Stop the old controller before enabling the new one.

## Build and test

Requirements: Python 3, Docker with Buildx and access to public source/toolchain registries. No Flutter SDK is used.

    python3 tools/validate.py
    python3 -m unittest discover -s tools -p 'test_*.py'
    python3 tools/build.py --platform linux/arm64 --tag rhythm-ha:review
    python3 tools/smoke.py --image rhythm-ha:review

The harness tests the real image through a synthetic Supervisor on a dual-stack Docker network. It checks the mobile listener's IPv4 and IPv6 health, authentication, enrolled access and revocation, with admin access remaining private. The fixture enforces `/core/api/` REST bearer authentication and `/core/websocket` authentication in the first WebSocket frame, so incorrect proxy URLs cannot pass as a working installation. It needs the 172.30.32.0/24 Docker subnet to be unused and fails on collision. Do not run it on the production HA host. Test containers and data are removed afterward.

## Build once, qualify, then promote

Build release candidates on the development machine. `source.lock.json` contains the candidate version and product revision. The build records those values, the packaging commit and a hash of image inputs in image labels. Commit changes before building. A pilot uses a unique `X.Y.Z-dev.NUMBER` version; production uses `X.Y.Z`. Never overwrite either version or use `latest` for installation.

With Docker Buildx, Python 3.11+ and Skopeo installed, build and export each architecture in sequence:

    python3 tools/build.py --platform linux/arm64 --tag rhythm-ha:candidate-arm64
    python3 tools/candidate.py export --image rhythm-ha:candidate-arm64 --output .build/arm64
    python3 tools/build.py --platform linux/amd64 --tag rhythm-ha:candidate-amd64
    python3 tools/candidate.py export --image rhythm-ha:candidate-amd64 --output .build/amd64
    python3 tools/candidate.py assemble .build/arm64 .build/amd64 --output .build/candidate.oci.tar

`export` runs the real-image smoke suite against the immutable local image ID and saves that same image into OCI storage, preserving its configuration and health check. Docker's containerd store identifies images by manifest digest; classic Docker identifies them by configuration digest. The receipt records which identity was tested and verifies it against the exported bytes. `assemble` verifies both exports and creates a multi-architecture archive without rebuilding. Retain `candidate.oci.tar`, `candidate.oci.json` and both adjacent smoke logs together. The receipt records artifact, manifest and configuration digests, source and packaging revisions, build-input hash, and whether each smoke run was native or emulated. A failed smoke or changed image cannot produce a successful export. Local ARM machines can build/test AMD64 through Docker emulation; this is recorded as emulated and does not replace required native qualification.

The separate authorized publisher consumes that exact archive and receipt, rejects an existing version tag, and preserves its digests. Production still requires HAOS qualification and native architecture evidence. A development pilot is a distinct prerelease, not a production release. Deployment artifacts are built locally. Automatic PR and master CI runs the Python contract and unit checks; native cloud image validation runs only when explicitly selected through the manual workflow's `build_images` option, which defaults to false. Public CI does not publish images and no cloud build is needed to create the local candidate.

After publication, verify public access and prepare the install metadata locally:

    python3 tools/promote.py --candidate .build/candidate.oci.json --check-only
    python3 tools/promote.py --candidate .build/candidate.oci.json

The promotion helper uses anonymous registry access, downloads both platform images by digest, verifies their provenance and content against the tested receipt, and checks the version tag again. A missing, private or substituted image leaves the catalog unchanged. Only after verification does it add `image: ghcr.io/sticktrk/rhythm-home-assistant`, set the matching catalog version and save `release.json`. Review and commit those metadata changes separately. Supervisor then pulls `ghcr.io/sticktrk/rhythm-home-assistant:<version>` and chooses its native architecture.

Before the first promotion, retain the existing development catalog version while preparing newer candidates in `source.lock.json`; do not advertise another source-build update to existing installations. After the first promotion, keep `rhythm/config.yaml` and `release.json` on the last published version while preparing newer source pins in `source.lock.json`. Reserve a newer candidate version whenever image inputs change. The validator rejects reusing a published version for changed inputs. Promote the catalog only after the newer image exists and passes anonymous verification; customers continue installing the previous working image meanwhile. Development source builds remain available through `tools/build.py` regardless of the catalog's image setting.

A direct multi-architecture build is also available for development, but does not create a smoke-tested release receipt:

    python3 tools/build.py --platform linux/amd64,linux/arm64 --output candidate.oci.tar

Product SHA updates change both Dockerfile arguments and the source lock together. `python3 tools/build.py --identity` prints the canonical candidate identity without building.

## Container boundary

Ingress:8099 → Nginx → local admin API:8787 → admin-only Rhythm:54449 → Supervisor → HA Core

Mobile LAN/mapped port or outbound tunnel → authenticated Rhythm:54448 → Supervisor → HA Core

Nginx accepts Ingress exclusively from Supervisor; the admin API separately verifies active HA administrator status. The mobile listener always requires a durable phone bearer for control and ignores Ingress identity headers. Single-use enrollment codes can only be created through authorized administration. Browser responses receive neither service token. Persistent state lives in /data/rhythm; the separate ephemeral admin token lives in /run/rhythm.

Only the mobile port is published. No host networking, privileged devices, host configuration mounts, Docker socket, Supervisor management API or password-validation API is requested. A pinned cloudflared binary provides the existing outbound tunnel.

Licensed under Apache-2.0.
