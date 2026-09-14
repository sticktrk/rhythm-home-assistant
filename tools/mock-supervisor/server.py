"""Synthetic HA REST/WebSocket fixture. No production credentials or networks."""
import base64
import hashlib
import json
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ADMIN = "a" * 32
ACTIVE = True

def read_exact(stream, size):
    data = b""
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise EOFError
        data += part
    return data

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        pass
    def reply(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        global ACTIVE
        if self.path == "/activate":
            ACTIVE = True; return self.reply({})
        if self.path == "/revoke":
            ACTIVE = False; return self.reply({})
        if self.headers.get("Upgrade", "").lower() == "websocket":
            return self.websocket()
        if self.path.endswith("/config"):
            return self.reply({"latitude": 51.5, "longitude": -0.12, "time_zone": "Europe/London"})
        if self.path.endswith("/states"):
            return self.reply([])
        return self.reply({"message": "API running."})
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.reply([])
    def send_frame(self, value, opcode=1):
        body = json.dumps(value).encode() if opcode == 1 else value
        header = bytes([128 | opcode])
        header += bytes([len(body)]) if len(body) < 126 else bytes([126]) + struct.pack("!H", len(body))
        self.wfile.write(header + body); self.wfile.flush()
    def websocket(self):
        key = self.headers["Sec-WebSocket-Key"]
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept); self.end_headers()
        self.send_frame({"type": "auth_required", "ha_version": "2026.9.0"})
        try:
            while True:
                first, second = read_exact(self.rfile, 2)
                length = second & 127
                if length == 126: length = struct.unpack("!H", read_exact(self.rfile, 2))[0]
                if length == 127: length = struct.unpack("!Q", read_exact(self.rfile, 8))[0]
                if length > 1048576: return
                mask = read_exact(self.rfile, 4) if second & 128 else None
                body = read_exact(self.rfile, length)
                if mask: body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
                opcode = first & 15
                if opcode == 8: return
                if opcode == 9: self.send_frame(body, 10); continue
                if opcode != 1: continue
                msg = json.loads(body)
                if msg["type"] == "auth":
                    self.send_frame({"type": "auth_ok", "ha_version": "2026.9.0"}); continue
                result = [{"id": ADMIN, "name": "Test administrator", "is_active": ACTIVE,
                           "is_owner": False, "group_ids": ["system-admin"]}] if msg["type"] == "config/auth/list" else []
                self.send_frame({"id": msg["id"], "type": "result", "success": True, "result": result})
        except (EOFError, ConnectionError):
            pass

ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
