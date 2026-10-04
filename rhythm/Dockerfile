# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
# Product revision is also recorded in source.lock.json and validated by CI.
ARG TARGETARCH
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS source
ARG RHYTHM_SOURCE_SHA=e3bf577c2c2c98d14275a29eb7f9442574f4fefd
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN mkdir /src && curl -fsSL --retry 3 "https://codeload.github.com/sticktrk/rhythm-os/tar.gz/${RHYTHM_SOURCE_SHA}" | tar xz --strip-components=1 -C /src

FROM rust:1.92.0-bookworm@sha256:e90e846de4124376164ddfbaab4b0774c7bdeef5e738866295e5a90a34a307a2 AS rust-build
ARG BUILD_VERSION
ARG RHYTHM_SOURCE_SHA
ARG RHYTHM_PACKAGING_REVISION
ARG RHYTHM_BUILD_INPUTS_SHA256
COPY --from=source /src /src
WORKDIR /src
RUN RHYTHM_IMAGE_VERSION="$BUILD_VERSION" \
    RHYTHM_PRODUCT_REVISION="$RHYTHM_SOURCE_SHA" \
    RHYTHM_PACKAGING_REVISION="$RHYTHM_PACKAGING_REVISION" \
    RHYTHM_BUILD_INPUTS_SHA256="$RHYTHM_BUILD_INPUTS_SHA256" \
    cargo build --locked --release -p rhythm-addon

FROM node:26-bookworm-slim@sha256:662933cf47f013bc8e4beb31a6116448427a82057ba7c42c97e4c5ba766504c2 AS ui-build
COPY --from=source /src/admin-ui /src/admin-ui
WORKDIR /src/admin-ui
RUN npm ci && npm run build:homeassistant

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS api-build
ARG TARGETARCH
ARG DART_VERSION=3.11.5
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip && rm -rf /var/lib/apt/lists/*
RUN case "$TARGETARCH" in \
      amd64) dart_arch=x64; checksum=57f3ab5ac24883060b1ff12bcdac472ed76563ec7364e88f8a6d41e4f0db075f ;; \
      arm64) dart_arch=arm64; checksum=50e9aba58f8717943854778a73074e63a80c42054355d35e2732a0cc0824a2fb ;; \
      *) exit 1 ;; esac; \
    url="https://storage.googleapis.com/dart-archive/channels/stable/release/${DART_VERSION}/sdk/dartsdk-linux-${dart_arch}-release.zip"; \
    curl -fsSL --retry 3 "$url" -o /tmp/dart.zip && \
    echo "$checksum  /tmp/dart.zip" | sha256sum -c - && \
    unzip -q /tmp/dart.zip -d /opt && rm /tmp/dart.zip
ENV PATH="/opt/dart-sdk/bin:${PATH}"
COPY --from=source /src/admin-api /src/admin-api
COPY --from=source /src/sdk /src/sdk
WORKDIR /src/admin-api
RUN dart pub get --enforce-lockfile && dart compile exe bin/local_server.dart -o /rhythm-admin-api

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS tunnel-build
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
# Immutable upstream release and independent per-architecture SHA-256 receipts.
RUN case "$TARGETARCH" in \
      amd64) checksum=77e26d8d900e0b8469f416239d14b5f296525fdf79fee6f511ef55609e3fbac2 ;; \
      arm64) checksum=aaeb2d7d0da3614634c7e03ab13487a1522c2e79165ed2929cfe23d5e95b326d ;; \
      *) exit 1 ;; esac; \
    curl -fsSL --retry 3 "https://github.com/cloudflare/cloudflared/releases/download/2026.9.3/cloudflared-linux-${TARGETARCH}" -o /cloudflared && \
    echo "$checksum  /cloudflared" | sha256sum -c - && chmod 755 /cloudflared && \
    curl -fsSL "https://raw.githubusercontent.com/cloudflare/cloudflared/2026.9.3/LICENSE" -o /cloudflared.LICENSE

FROM ghcr.io/home-assistant/base-debian:bookworm@sha256:60cd882d5200157082e568a0b775cca0d9cb5704452ada3cf6f206c4dd6d83c5 AS runtime
ARG RHYTHM_SOURCE_SHA=e3bf577c2c2c98d14275a29eb7f9442574f4fefd
ARG BUILD_VERSION=development
LABEL org.opencontainers.image.title="Rhythm for Home Assistant" \
      org.opencontainers.image.source="https://github.com/sticktrk/rhythm-home-assistant" \
      io.rhythm.product.revision="${RHYTHM_SOURCE_SHA}" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.name="Rhythm" \
      io.hass.description="Adaptive lighting with mobile control and Home Assistant administration" \
      io.hass.url="https://github.com/sticktrk/rhythm-home-assistant"
RUN apt-get update && apt-get install -y --no-install-recommends nginx-light ca-certificates libssl3 libstdc++6 curl && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default
COPY --from=tunnel-build /cloudflared /usr/local/bin/cloudflared
COPY --from=tunnel-build /cloudflared.LICENSE /usr/share/doc/cloudflared/LICENSE
COPY --from=rust-build /src/target/release/rhythm-addon /usr/local/bin/rhythm-addon
COPY --from=api-build /rhythm-admin-api /usr/local/bin/rhythm-admin-api
COPY --from=ui-build /src/admin-ui/dist-homeassistant/ /opt/rhythm/ui/
COPY rootfs /
RUN chmod 755 /etc/cont-init.d/10-rhythm /etc/services.d/*/run /etc/services.d/*/finish && nginx -t
ENV RHYTHM_STATE_PATH=/data/rhythm RHYTHM_ADDON_API_TOKEN_FILE=/run/rhythm/api-token
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD curl -fsS http://127.0.0.1:8787/health >/dev/null || exit 1

# Supervisor calls ARM64 "aarch64"; Docker calls it "arm64". Select the final
# metadata per platform, including for a multi-platform local OCI build.
FROM runtime AS platform-amd64
LABEL io.hass.arch="amd64"
FROM runtime AS platform-arm64
LABEL io.hass.arch="aarch64"
FROM platform-${TARGETARCH}
