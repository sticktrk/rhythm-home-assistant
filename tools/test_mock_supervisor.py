"""Keep the real-image fixture faithful to Supervisor's proxy contract."""
import base64
import http.client
import importlib.util
import json
import socket
import struct
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "mock_supervisor", Path(__file__).parent / "mock-supervisor/server.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class SupervisorProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), fixture.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_rest_requires_current_supervisor_credential(self):
        for token in (None, "wrong-token"):
            headers = {} if token is None else {"Authorization": "Bearer " + token}
            self.assertEqual(self.request("/core/api/config", headers)[0], 401)
        status, body = self.request("/core/api/config", {"Authorization": "Bearer " + fixture.TOKEN})
        self.assertEqual(status, 200)
        self.assertEqual(body["time_zone"], "Europe/London")

    def test_rest_rejects_non_supervisor_paths(self):
        for path in ("/api/config", "/core/config", "/anything/states"):
            self.assertEqual(self.request(path, {"Authorization": "Bearer " + fixture.TOKEN})[0], 404)

    def test_websocket_rejects_api_prefixed_and_direct_core_paths(self):
        for path in ("/core/api/websocket", "/api/websocket"):
            status, _ = self.request(path, {
                "Authorization": "Bearer " + fixture.TOKEN,
                "Upgrade": "websocket",
            })
            self.assertEqual(status, 404)

    def websocket_auth(self, token, commands=(), http_token=None):
        with socket.create_connection(self.server.server_address, timeout=2) as connection:
            stream = connection.makefile("rb")
            authorization = "" if http_token is None else "Authorization: Bearer " + http_token + "\r\n"
            connection.sendall((
                "GET /core/websocket HTTP/1.1\r\nHost: supervisor\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Key: " + base64.b64encode(b"synthetic-key-16!").decode() + "\r\n"
                + authorization + "\r\n"
            ).encode())
            self.assertIn(b"101", stream.readline())
            while stream.readline() != b"\r\n":
                pass

            def frame():
                first, second = fixture.read_exact(stream, 2)
                self.assertEqual(first, 129)
                length = struct.unpack("!H", fixture.read_exact(stream, 2))[0] if second == 126 else second
                return json.loads(fixture.read_exact(stream, length))

            def send(payload):
                payload = json.dumps(payload).encode()
                mask = b"test"
                header = bytes([129, 128 | len(payload)]) if len(payload) < 126 else b"\x81\xfe" + struct.pack("!H", len(payload))
                connection.sendall(header + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))

            self.assertEqual(frame()["type"], "auth_required")
            send({"type": "auth", "access_token": token})
            response = frame()
            replies = []
            for command in commands:
                send(command)
                replies.append(frame())
            connection.sendall(b"\x88\x80test")
            stream.close()
            return replies if commands else response

    def test_websocket_accepts_headerless_upgrade_with_valid_frame_token(self):
        self.assertEqual(self.websocket_auth(fixture.TOKEN)["type"], "auth_ok")

    def test_http_bearer_does_not_authorize_an_invalid_websocket_frame(self):
        self.assertEqual(self.websocket_auth("wrong-token", http_token=fixture.TOKEN)["type"], "auth_invalid")

    def test_http_bearer_does_not_replace_websocket_frame_token(self):
        self.assertEqual(self.websocket_auth(None, http_token=fixture.TOKEN)["type"], "auth_invalid")

    def test_websocket_authentication_uses_frame_not_http_header(self):
        self.assertEqual(self.websocket_auth(fixture.TOKEN, http_token="wrong-token")["type"], "auth_ok")

    def test_service_calls_return_distinct_command_contexts_and_record_targets(self):
        service_data = {"entity_id": fixture.LIGHT["entity_id"], "brightness": 120}
        commands = [{"id": index, "type": "call_service", "domain": "light",
                     "service": "turn_on", "service_data": service_data} for index in (1, 2)]
        replies = self.websocket_auth(fixture.TOKEN, commands)
        self.assertEqual([reply["id"] for reply in replies], [1, 2])
        self.assertTrue(all(reply["success"] for reply in replies))
        contexts = [reply["result"]["context"]["id"] for reply in replies]
        self.assertNotEqual(contexts[0], contexts[1])
        self.assertEqual(fixture.CALLS[-1]["body"], service_data)
        self.assertEqual(fixture.CALLS[-1]["transport"], "websocket")


if __name__ == "__main__":
    unittest.main()
