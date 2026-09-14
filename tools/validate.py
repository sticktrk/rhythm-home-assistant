#!/usr/bin/env python3
"""Validate the add-on's narrowly scoped packaging contract."""
import re
from pathlib import Path
from build import ROOT, load_lock

def validate():
    load_lock()
    text = (ROOT / "rhythm/config.yaml").read_text()
    scalars = dict(re.findall(r"^([a-z_]+):\s*([^\n]*)$", text, re.M))
    for key, value in {"slug": "rhythm", "ingress": "true", "ingress_port": "8099",
                       "panel_admin": "true", "homeassistant_api": "true", "hassio_api": "false",
                       "auth_api": "false", "init": "false", "backup": "cold"}.items():
        assert scalars.get(key) == value, (key, scalars.get(key))
    assert re.findall(r"^  - ([a-z0-9]+)$", text, re.M) == ["aarch64", "amd64"]
    assert not {"ports", "host_network", "host_dbus", "host_pid", "host_ipc", "docker_api",
                "privileged", "devices", "map", "usb", "uart", "gpio", "apparmor"} & scalars.keys()
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
