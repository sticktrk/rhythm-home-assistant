"""Loopback browser inspection gateway for synthetic Ingress only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
import urllib.error

PREFIX = '/api/hassio_ingress/review_token'

class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def forward(self):
        path = self.path.removeprefix(PREFIX)
        headers = dict(self.headers)
        headers.update({'X-Ingress-Path': PREFIX, 'X-Remote-User-Id': 'a' * 32,
                        'X-Forwarded-Host': self.headers['Host'], 'X-Forwarded-Proto': 'http'})
        body = self.rfile.read(int(self.headers.get('Content-Length', 0))) if self.command == 'POST' else None
        request = urllib.request.Request('http://172.30.32.4:8099' + (path or '/'), data=body, headers=headers)
        try: response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error: response = error
        data = response.read()
        self.send_response(response.status)
        for name, value in response.headers.items():
            if name.lower() not in ('content-length', 'connection', 'transfer-encoding'):
                self.send_header(name, value)
        self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    do_GET = forward
    do_POST = forward

ThreadingHTTPServer(('0.0.0.0', 8080), Gateway).serve_forever()
