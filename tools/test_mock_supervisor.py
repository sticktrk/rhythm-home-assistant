"""Keep the real-image fixture faithful to Supervisor's proxy contract."""
import base64
import http.client
import importlib.util
import json
import socket
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

    def test_websocket_requires_supervisor_credential_before_upgrade(self):
        self.assertEqual(self.request("/core/websocket", {"Upgrade": "websocket"})[0], 401)

    def websocket_auth(self, token):
        with socket.create_connection(self.server.server_address, timeout=2) as connection:
            stream = connection.makefile("rb")
            connection.sendall((
                "GET /core/websocket HTTP/1.1\r\nHost: supervisor\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Key: " + base64.b64encode(b"synthetic-key-16!").decode() + "\r\n"
                "Authorization: Bearer " + fixture.TOKEN + "\r\n\r\n"
            ).encode())
            self.assertIn(b"101", stream.readline())
            while stream.readline() != b"\r\n":
                pass

            def frame():
                first, second = fixture.read_exact(stream, 2)
                self.assertEqual(first, 129)
                self.assertLess(second, 126)
                return json.loads(fixture.read_exact(stream, second))

            self.assertEqual(frame()["type"], "auth_required")
            payload = json.dumps({"type": "auth", "access_token": token}).encode()
            mask = b"test"
            connection.sendall(bytes([129, 128 | len(payload)]) + mask +
                               bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))
            response = frame()
            connection.sendall(b"\x88\x80test")
            stream.close()
            return response

    def test_websocket_authenticates_the_message_token(self):
        self.assertEqual(self.websocket_auth(fixture.TOKEN)["type"], "auth_ok")
        self.assertEqual(self.websocket_auth("wrong-token")["type"], "auth_invalid")


if __name__ == "__main__":
    unittest.main()
