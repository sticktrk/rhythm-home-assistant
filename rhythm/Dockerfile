# syntax=docker/dockerfile:1
# Product revision is also recorded in source.lock.json and validated by CI.
FROM debian:bookworm-slim AS source
ARG RHYTHM_SOURCE_SHA=14822b1ab9dde52adba0f484b525b577437a2eb5
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN mkdir /src && curl -fsSL --retry 3 "https://codeload.github.com/sticktrk/rhythm-os/tar.gz/${RHYTHM_SOURCE_SHA}" | tar xz --strip-components=1 -C /src

FROM rust:1.92.0-bookworm AS rust-build
COPY --from=source /src /src
WORKDIR /src
RUN cargo build --locked --release -p rhythm-addon

FROM node:24-bookworm-slim AS ui-build
COPY --from=source /src/admin-ui /src/admin-ui
WORKDIR /src/admin-ui
RUN npm ci && npm run build:homeassistant

FROM debian:bookworm-slim AS api-build
ARG TARGETARCH
ARG DART_VERSION=3.11.5
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip && rm -rf /var/lib/apt/lists/*
RUN case "$TARGETARCH" in amd64) dart_arch=x64 ;; arm64) dart_arch=arm64 ;; *) exit 1 ;; esac; \
    url="https://storage.googleapis.com/dart-archive/channels/stable/release/${DART_VERSION}/sdk/dartsdk-linux-${dart_arch}-release.zip"; \
    curl -fsSL --retry 3 "$url" -o /tmp/dart.zip && \
    curl -fsSL "$url.sha256sum" | cut -d ' ' -f 1 > /tmp/dart.sha256 && \
    echo "$(cat /tmp/dart.sha256)  /tmp/dart.zip" | sha256sum -c - && \
    unzip -q /tmp/dart.zip -d /opt && rm /tmp/dart.zip
ENV PATH="/opt/dart-sdk/bin:${PATH}"
COPY --from=source /src/admin-api /src/admin-api
COPY --from=source /src/sdk /src/sdk
WORKDIR /src/admin-api
RUN dart pub get --enforce-lockfile && dart compile exe bin/local_server.dart -o /rhythm-admin-api

FROM debian:bookworm-slim AS tunnel-build
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

FROM ghcr.io/home-assistant/base-debian:bookworm@sha256:60cd882d5200157082e568a0b775cca0d9cb5704452ada3cf6f206c4dd6d83c5
ARG RHYTHM_SOURCE_SHA=14822b1ab9dde52adba0f484b525b577437a2eb5
LABEL org.opencontainers.image.title="Rhythm for Home Assistant" \
      org.opencontainers.image.source="https://github.com/sticktrk/rhythm-home-assistant" \
      io.rhythm.product.revision="${RHYTHM_SOURCE_SHA}"
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
