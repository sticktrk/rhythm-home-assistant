#!/usr/bin/env python3
"""Exercise the real image behind a synthetic Supervisor network (no HAOS claim)."""
import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "a" * 32
PREFIX = "/api/hassio_ingress/review_token"
TOKEN = "synthetic-supervisor-token-for-tests"

def docker(*args, capture=True):
    return subprocess.check_output(["docker", *args], text=True).strip() if capture else subprocess.run(["docker", *args], check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="rhythm-ha:review")
    parser.add_argument("--inspect", action="store_true", help="Keep synthetic containers and expose a loopback browser gateway on port 18099")
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:8]
    network = "rhythm-test-" + suffix
    addon, supervisor, client = [network + "-" + role for role in ("addon", "supervisor", "client")]
    volume = network + "-data"
    created = []
    image = "rhythm-supervisor-fixture:local"
    docker("build", "-q", "-t", image, str(ROOT / "tools/mock-supervisor"))
    # Fail on a subnet collision; never reuse or modify an existing HA network.
    docker("network", "create", "--subnet", "172.30.32.0/24", network)
    try:
        docker("volume", "create", volume)
        docker("run", "-d", "--name", supervisor, "--network", network, "--ip", "172.30.32.3",
               "--network-alias", "supervisor", image); created.append(supervisor)
        docker("run", "-d", "--name", client, "--network", network, "--ip", "172.30.32.2",
               *(["-p", "127.0.0.1:18099:8080"] if args.inspect else []),
               image, "python", "/gateway.py"); created.append(client)
        docker("run", "-d", "--name", addon, "--network", network, "--ip", "172.30.32.4",
               "-e", "SUPERVISOR_TOKEN=" + TOKEN, "-v", volume + ":/data", args.image); created.append(addon)
        def request(path, body=None, headers=None, from_container=client, host="172.30.32.4:8099"):
            h = {"X-Ingress-Path": PREFIX, "X-Remote-User-Id": ADMIN,
                 "X-Forwarded-Host": "home.test:8123", "X-Forwarded-Proto": "http",
                 "Origin": "http://home.test:8123", "X-Rhythm-Local-Request": "1",
                 "Content-Type": "application/json"}
            h.update(headers or {})
            script = """import json,sys,urllib.request,urllib.error
args=json.loads(sys.argv[1])
req=urllib.request.Request(args['url'],headers=args['headers'],data=None if args['body'] is None else json.dumps(args['body']).encode())
try: response=urllib.request.urlopen(req,timeout=10)
except urllib.error.HTTPError as error: response=error
except urllib.error.URLError:
 print(json.dumps({'status':0,'headers':{},'body':'Service starting'})); sys.exit(0)
raw=response.read().decode()
try: body=json.loads(raw)
except ValueError: body=raw
print(json.dumps({'status':response.status,'headers':dict(response.headers),'body':body}))
"""
            return json.loads(docker("exec", from_container, "python", "-c", script,
                                     json.dumps({"url": "http://" + host + path, "headers": h, "body": body})))
        def wait_ready():
            for _ in range(60):
                try:
                    response = request("/api/session")
                    if response["status"] == 200 and response["body"].get("status"):
                        return response["body"]
                except subprocess.CalledProcessError:
                    pass
                if docker("inspect", "-f", "{{.State.Running}}", addon) != "true":
                    raise AssertionError("An essential service exited: " + docker("logs", addon))
                time.sleep(1)
            raise AssertionError("Image did not become ready")
        session = wait_ready()
        assert session["deployment"] == "home_assistant_addon"
        assert session["status"]["connection"]["configured_count"] == 1
        assert not session["status"]["light_breaker_enabled"]
        assert TOKEN not in json.dumps(session)
        for route in ("/", "/nodes", "/profiles", "/system"):
            result = request(route)
            assert result["status"] == 200, result
            assert 'href="' + PREFIX + '/"' in result["body"]
            assert "__RHYTHM_BASE__" not in result["body"]
            assert "Content-Security-Policy" in result["headers"]
            assert "flutter" not in result["body"].lower()
        assert request("/", from_container=supervisor)["status"] == 403
        assert request("/", headers={"X-Ingress-Path": '"><script>'})["status"] == 400
        assert request("/api/session", headers={"X-Remote-User-Id": ""})["status"] == 403
        assert request("/api/session", headers={"X-Remote-User-Id": "b" * 32})["status"] == 403

        def proxy(method, path, body=None, **headers):
            op = {"method": method, "path": path}
            if method != "GET":
                identity = proxy("GET", "api/state")["body"]["body"]["server_instance_id"]
                op.update(requestId="ha-review-" + uuid.uuid4().hex, expectedServerInstanceId=identity)
            if body is not None: op["body"] = body
            return request("/api/local/device-admin/proxy", op, headers)

        assert proxy("GET", "api/addon/lights")["body"]["body"]["entities"] == []
        assert proxy("PUT", "api/hub/credentials", {})["body"]["statusCode"] == 403
        assert proxy("PUT", "api/backup", {})["body"]["statusCode"] == 403
        assert proxy("PUT", "api/light-breaker", {"enabled": False}, Origin="http://evil.test")["status"] == 403
        assert proxy("PUT", "api/addon/lights", {"entities": [], "expected_entities": []})["body"]["statusCode"] == 200
        assert proxy("PUT", "api/addon/lights", {"entities": [], "expected_entities": ["light.stale"]})["body"]["statusCode"] == 409
        request("/revoke", host="supervisor:80")
        assert proxy("PUT", "api/light-breaker", {"enabled": False})["status"] == 403
        request("/activate", host="supervisor:80")
        old_token = docker("exec", addon, "cat", "/run/rhythm/api-token")
        assert TOKEN not in docker("exec", addon, "cat", "/data/rhythm/hub_credentials.json")
        assert "credential_source" in docker("exec", addon, "cat", "/data/rhythm/hub_credentials.json")
        docker("exec", addon, "sh", "-c", "printf '{\"fixture\":true}' > /data/options.json")
        docker("restart", addon)
        wait_ready()
        assert old_token != docker("exec", addon, "cat", "/run/rhythm/api-token")
        assert json.loads(docker("exec", addon, "cat", "/data/options.json"))["fixture"]
        assert proxy("GET", "api/addon/lights")["body"]["body"]["entities"] == []
        assert not docker("exec", addon, "sh", "-c", "command -v flutter || true")
        reset = proxy("POST", "api/factory-reset", {})
        assert reset["body"]["statusCode"] == 200, reset
        for _ in range(20):
            if docker("inspect", "-f", "{{.State.Running}}", addon) == "false": break
            time.sleep(1)
        assert docker("inspect", "-f", "{{.State.Running}}", addon) == "false", "Reset did not stop the container"
        assert docker("inspect", "-f", "{{.State.ExitCode}}", addon) == "1"
        docker("start", addon)
        assert not wait_ready()["status"]["light_breaker_enabled"]
        assert json.loads(docker("exec", addon, "cat", "/data/options.json"))["fixture"]
        assert proxy("GET", "api/addon/lights")["body"]["body"]["entities"] == []
        print("PASS: factory reset stops essential services, restarts paused and preserves Supervisor options.")
        print("PASS: real image, nested Ingress, trusted identity, revocation, CSRF, forbidden routes, selection CAS, persistence and token rotation.")
    finally:
        if args.inspect:
            print("Inspection URL: http://127.0.0.1:18099" + PREFIX + "/overview")
            print("Cleanup containers: " + " ".join(created) + "; volume: " + volume + "; network: " + network)
        for name in reversed(created) if not args.inspect else []:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not args.inspect:
            subprocess.run(["docker", "volume", "rm", volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "network", "rm", network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    main()
