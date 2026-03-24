#!/usr/bin/env python3
"""
심리테스트 웹앱 서버
- 정적 파일 서빙 (index.html, admin.html)
- 테스트 데이터 CRUD API (/api/tests)
- JSON 파일 기반 저장 (tests.json)
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import uuid

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests.json')
PORT = int(os.environ.get('PORT', 8080))


def load_tests():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_tests(tests):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(tests, f, ensure_ascii=False, indent=2)


class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/tests':
            tests = load_tests()
            self._json_response(tests)
        elif parsed.path == '/api/inactive':
            inactive = self._load_inactive()
            self._json_response(inactive)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/tests':
            body = self._read_body()
            if body is None:
                return
            tests = load_tests()
            # Generate ID if not present
            if not body.get('id'):
                body['id'] = 'custom_' + uuid.uuid4().hex[:10]
            # Check duplicate ID, update if exists
            existing = next((i for i, t in enumerate(tests) if t['id'] == body['id']), None)
            if existing is not None:
                tests[existing] = body
            else:
                tests.append(body)
            save_tests(tests)
            self._json_response({'ok': True, 'id': body['id']})

        elif parsed.path == '/api/inactive':
            body = self._read_body()
            if body is None:
                return
            self._save_inactive(body)
            self._json_response({'ok': True})

        else:
            self._json_response({'error': 'Not found'}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith('/api/tests/'):
            test_id = parsed.path.split('/api/tests/')[1]
            tests = load_tests()
            tests = [t for t in tests if t['id'] != test_id]
            save_tests(tests)
            self._json_response({'ok': True})
        else:
            self._json_response({'error': 'Not found'}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _read_body(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            return json.loads(raw.decode('utf-8'))
        except Exception as e:
            self._json_response({'error': str(e)}, 400)
            return None

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _load_inactive(self):
        path = DATA_FILE.replace('tests.json', 'inactive.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _save_inactive(self, data):
        path = DATA_FILE.replace('tests.json', 'inactive.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def log_message(self, format, *args):
        if '/api/' in str(args[0]):
            super().log_message(format, *args)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(DATA_FILE):
        save_tests([])

    server = HTTPServer(('0.0.0.0', port), AppHandler)
    print(f'서버 시작: http://0.0.0.0:{port}')
    server.serve_forever()
