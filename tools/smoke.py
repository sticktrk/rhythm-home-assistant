#!/usr/bin/env python3
"""Exercise the real image behind a synthetic Supervisor network (no HAOS claim)."""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
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
    ipv6_prefix = "fdf4:522c:" + suffix[:4] + ":" + suffix[4:]
    mobile_ipv6 = ipv6_prefix + "::4"
    addon, supervisor, client = [network + "-" + role for role in ("addon", "supervisor", "client")]
    volume = network + "-data"
    created = []
    image = "rhythm-supervisor-fixture:local"
    docker("build", "-q", "-t", image, str(ROOT / "tools/mock-supervisor"))
    # Fail on a subnet collision; never reuse or modify an existing HA network.
    docker("network", "create", "--subnet", "172.30.32.0/24", "--ipv6",
           "--subnet", ipv6_prefix + "::/64", network)
    try:
        docker("volume", "create", volume)
        docker("run", "-d", "--name", supervisor, "--network", network, "--ip", "172.30.32.3",
               "--network-alias", "supervisor", image); created.append(supervisor)
        docker("run", "-d", "--name", client, "--network", network, "--ip", "172.30.32.2",
               *(["-p", "127.0.0.1:18099:8080"] if args.inspect else []),
               image, "python", "/gateway.py"); created.append(client)
        docker("run", "-d", "--name", addon, "--network", network, "--ip", "172.30.32.4", "--ip6", mobile_ipv6,
               "-p", "127.0.0.1::54448", "-e", "SUPERVISOR_TOKEN=" + TOKEN, "-v", volume + ":/data", args.image); created.append(addon)
        def mapped_state(token=None):
            # Docker may allocate a different ephemeral host port after restart.
            mapped_port = docker("port", addon, "54448/tcp").rsplit(":", 1)[1]
            headers = {"Authorization": "Bearer " + token} if token else {}
            req = urllib.request.Request("http://127.0.0.1:" + mapped_port + "/api/state", headers=headers)
            try: response = urllib.request.urlopen(req, timeout=10)
            except urllib.error.HTTPError as error: response = error
            with response:
                return response.status, json.loads(response.read())
        def request(path, body=None, headers=None, from_container=client, host="172.30.32.4:8099"):
            h = {"X-Ingress-Path": PREFIX, "X-Remote-User-Id": ADMIN,
                 "X-Forwarded-Host": "home.test:8123", "X-Forwarded-Proto": "http",
                 "Origin": "http://home.test:8123", "X-Rhythm-Local-Request": "1",
                 "Content-Type": "application/json"}
            h.update(headers or {})
            script = """import json,sys,urllib.request,urllib.error
args=json.loads(sys.argv[1])
req=urllib.request.Request(args['url'],headers=args['headers'],data=None if args['body'] is None else json.dumps(args['body']).encode())
try: response=urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=10)
except urllib.error.HTTPError as error: response=error
except urllib.error.URLError as error:
 print(json.dumps({'status':0,'headers':{},'body':'Service unreachable','error':type(error.reason).__name__})); sys.exit(0)
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
        labels = json.loads(docker("image", "inspect", args.image))[0]["Config"]["Labels"]
        expected_build = {
            "image_version": labels["io.hass.version"],
            "product_revision": labels["io.rhythm.product.revision"],
            "packaging_revision": labels["io.rhythm.packaging.revision"],
            "build_inputs_sha256": labels["io.rhythm.build.inputs"],
        }
        build = session["status"]["build"]
        assert build["schema_version"] == 1 and build["product_version"]
        assert {key: build[key] for key in expected_build} == expected_build
        admin_health = json.loads(docker("exec", addon, "curl", "-fsS", "http://127.0.0.1:8787/health"))
        assert admin_health["build"] == build
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

        def proxy(method, path, body=None, expected_status=200, **headers):
            op = {"method": method, "path": path}
            if method != "GET":
                identity = proxy("GET", "api/state")["body"]["body"]["server_instance_id"]
                op.update(requestId="ha-review-" + uuid.uuid4().hex, expectedServerInstanceId=identity)
            if body is not None: op["body"] = body
            response = request("/api/local/device-admin/proxy", op, headers)
            assert response["status"] == expected_status, (method, path, response)
            if expected_status == 200:
                assert isinstance(response["body"], dict) and {"body", "statusCode"} <= response["body"].keys(), (method, path, response)
            return response

        # Mobile and Ingress credentials are separate. HA identity headers do
        # not authorize the mobile listener, even from the trusted gateway IP.
        mobile_host = "172.30.32.4:54448"
        mobile_hosts = [mobile_host, "[" + mobile_ipv6 + "]:54448"]
        # HA's default bridge is dual-stack: published IPv6 traffic targets
        # the container's IPv6 address, bypassing an IPv4-only listener.
        for host in mobile_hosts:
            for path, expected in (("/health", 200), ("/api/state", 401), ("/api/events", 401)):
                response = request(path, host=host)
                assert response["status"] == expected, ("Mobile listener", host, path, response)
                if path == "/health":
                    assert response["body"]["build"] == build
        assert mapped_state()[0] == 401
        assert request("/api/auth/claim", {}, host=mobile_host)["status"] in (401, 403)
        assert request("/api/addon/enrollment", {}, host=mobile_host)["status"] in (401, 403, 404)
        enrollment_response = proxy("POST", "api/addon/enrollment", {})["body"]
        assert enrollment_response["statusCode"] == 200, enrollment_response
        enrollment = enrollment_response["body"]
        assert enrollment["server_instance_id"]
        exchange = {"code": enrollment["code"], "server_instance_id": enrollment["server_instance_id"], "label": "Synthetic phone"}
        issued = request("/api/addon/enrollment/exchange", exchange, host=mobile_hosts[1])
        assert issued["status"] == 200, issued
        phone_token = issued["body"]["token"]
        phone_id = issued["body"]["token_id"]
        phone_headers = {"Authorization": "Bearer " + phone_token}
        for host in mobile_hosts:
            assert request("/api/state", headers=phone_headers, host=host)["status"] == 200, host
        mapped_status, mapped_body = mapped_state(phone_token)
        assert mapped_status == 200 and mapped_body["server_instance_id"] == enrollment["server_instance_id"]
        assert request("/api/addon/enrollment/exchange", exchange, host=mobile_host)["status"] == 401
        assert request("/api/session", headers={**phone_headers, "X-Remote-User-Id": ""})["status"] == 403
        assert request("/api/state", headers=phone_headers, host="172.30.32.4:54449")["status"] == 0
        assert request("/api/state", headers=phone_headers, host="[" + mobile_ipv6 + "]:54449")["status"] == 0
        assert phone_token not in json.dumps(proxy("GET", "api/addon/mobile-tokens"))

        assert proxy("GET", "api/addon/lights")["body"]["body"]["entities"] == []
        assert proxy("PUT", "api/hub/credentials", {})["body"]["statusCode"] == 403
        assert proxy("PUT", "api/backup", {})["body"]["statusCode"] == 403
        assert proxy("PUT", "api/light-breaker", {"enabled": False}, expected_status=403, Origin="http://evil.test")["status"] == 403
        for _ in range(30):
            selection = proxy("GET", "api/addon/lights")["body"]["body"]
            if selection.get("snapshot_ready"): break
            time.sleep(1)
        assert selection.get("snapshot_ready"), "HA inventory never became ready"
        assert len(selection["available"]) == 1, selection
        light = selection["available"][0]
        assert light["entity_id"] == "light.reviewed_fixture" and light["reviewable"], light
        assert light["identity"]["registry_id"] == "fixture-registry-id", light
        assert request("/fixture/calls", host="supervisor:80")["body"] == [], "Unselected lights received commands"
        assert proxy("PUT", "api/addon/lights", {"entities": [], "expected_entities": []})["body"]["statusCode"] == 428
        assert proxy("PUT", "api/addon/lights", {"entities": [], "expected_entities": [], "expected_snapshot_revision": selection["snapshot_revision"]})["body"]["statusCode"] == 200
        assert proxy("PUT", "api/addon/lights", {"entities": [], "expected_entities": ["light.stale"], "expected_snapshot_revision": selection["snapshot_revision"]})["body"]["statusCode"] == 409
        assert proxy("PUT", "api/addon/lights", {"entities": [light["entity_id"]], "expected_entities": [], "expected_snapshot_revision": selection["snapshot_revision"]})["body"]["statusCode"] == 200
        assert proxy("PUT", "api/light-breaker", {"enabled": True})["body"]["statusCode"] == 200
        nodes = proxy("GET", "api/state")["body"]["body"]["nodes"]
        room = next(node for node in nodes if node["name"] == "Fixture room" and node["kind"] == "room")
        action = proxy("PUT", "api/nodes/action", {"node_id": room["id"], "action": "off"})["body"]
        assert action["statusCode"] == 200, action
        # Node actions queue dispatch; observe its result without replaying the
        # mutation or assuming the worker already ran when HTTP returns.
        dispatch_deadline = time.monotonic() + 10
        while True:
            calls = request("/fixture/calls", host="supervisor:80")["body"]
            if any(call["path"] == "/core/api/services/light/turn_off" for call in calls): break
            if time.monotonic() >= dispatch_deadline: break
            time.sleep(0.1)
        assert any(call["path"] == "/core/api/services/light/turn_off" for call in calls), calls
        assert all(call.get("transport") == "websocket" for call in calls), calls
        assert all(call["body"].get("entity_id") in (light["entity_id"], [light["entity_id"]]) for call in calls), calls
        request("/revoke", host="supervisor:80")
        assert proxy("PUT", "api/light-breaker", {"enabled": False}, expected_status=403)["status"] == 403
        request("/activate", host="supervisor:80")
        old_token = docker("exec", addon, "cat", "/run/rhythm/api-token")
        assert TOKEN not in docker("exec", addon, "cat", "/data/rhythm/hub_credentials.json")
        assert "credential_source" in docker("exec", addon, "cat", "/data/rhythm/hub_credentials.json")
        docker("exec", addon, "sh", "-c", "printf '{\"fixture\":true}' > /data/options.json")
        docker("restart", addon)
        assert wait_ready()["status"]["light_breaker_enabled"], "Restart lost reviewed enablement intent"
        assert old_token != docker("exec", addon, "cat", "/run/rhythm/api-token")
        for host in mobile_hosts:
            assert request("/api/state", headers=phone_headers, host=host)["status"] == 200, host
        assert request("/api/state", headers={"Authorization": "Bearer " + old_token}, host=mobile_host)["status"] == 401
        assert proxy("DELETE", "api/addon/mobile-tokens/" + phone_id)["body"]["statusCode"] == 200
        for host in mobile_hosts:
            assert request("/api/state", headers=phone_headers, host=host)["status"] == 401, host
        assert mapped_state(phone_token)[0] == 401
        assert json.loads(docker("exec", addon, "cat", "/data/options.json"))["fixture"]
        for _ in range(30):
            restored = proxy("GET", "api/addon/lights")["body"]["body"]
            if restored.get("snapshot_ready"): break
            time.sleep(1)
        assert restored["entities"] == ["light.reviewed_fixture"], restored
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
        print("PASS: mobile enrollment, single use, isolated listeners, restart continuity and revocation.")
        print("PASS: dual-stack mobile health, authentication, enrolled access and revocation; admin listener remains private.")
        print("PASS: real image, nested Ingress, trusted identity, revocation, CSRF, forbidden routes, selection CAS, persistence and token rotation.")
    except Exception:
        if addon in created:
            print(docker("logs", "--tail", "120", addon), flush=True)
        raise
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
