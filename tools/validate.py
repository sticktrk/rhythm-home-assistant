#!/usr/bin/env python3
"""Validate the add-on's narrowly scoped packaging contract."""
import re
from pathlib import Path
from build import ROOT, load_lock

def validate():
    lock = load_lock()
    text = (ROOT / "rhythm/config.yaml").read_text()
    scalars = dict(re.findall(r"^([a-z_]+):\s*([^\n]*)$", text, re.M))
    for key, value in {"slug": "rhythm", "ingress": "true", "ingress_port": "8099",
                       "panel_admin": "true", "homeassistant_api": "true", "hassio_api": "false",
                       "auth_api": "false", "init": "false", "backup": "cold"}.items():
        assert scalars.get(key) == value, (key, scalars.get(key))
    assert re.findall(r"^  - ([a-z0-9]+)$", text, re.M) == ["aarch64", "amd64"]
    assert not {"host_network", "host_dbus", "host_pid", "host_ipc", "docker_api",
                "privileged", "devices", "map", "usb", "uart", "gpio", "apparmor"} & scalars.keys()
    assert re.search(r"^ports:\n((?:  .*\n)+)", text, re.M)[1] == "  54448/tcp: 54448\n"
    dockerfile = (ROOT / "rhythm/Dockerfile").read_text()
    assert "COPY --from=tunnel-build /cloudflared /usr/local/bin/cloudflared" in dockerfile
    assert "sha256sum -c -" in dockerfile
    assert "cloudflared/releases/download/" + lock["cloudflared"]["version"] + "/" in dockerfile
    for digest in lock["cloudflared"]["sha256"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest) and digest in dockerfile
    assert re.fullmatch(r'"[0-9]+\.[0-9]+\.[0-9]+"', scalars["version"])
    nginx = (ROOT / "rhythm/rootfs/etc/nginx/nginx.conf").read_text()
    assert "allow 172.30.32.2;" in nginx and "deny all;" in nginx
    assert "proxy_next_upstream off;" in nginx
    assert "sub_filter '__RHYTHM_BASE__' $rhythm_base;" in nginx
    for run in (ROOT / "rhythm/rootfs/etc/services.d").glob("*/run"):
        assert run.read_text().startswith("#!/usr/bin/with-contenv bash")
    print("Immutable source, HA manifest, permission and Ingress contracts passed.")

if __name__ == "__main__":
    validate()
