#!/usr/bin/env python3
"""
심리테스트 웹앱 서버
- 정적 파일 서빙 (index.html, admin.html)
- 테스트 데이터 CRUD API (/api/tests)
- Supabase DB 기반 저장 (환경변수 없으면 로컬 JSON 폴백)
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import URLError
import uuid

PORT = int(os.environ.get('PORT', 8080))
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# ── Supabase helpers ──────────────────────────────

def _sb_request(method, table, params='', body=None):
    """Supabase REST API 호출 (urllib만 사용)"""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except URLError as e:
        print(f"[Supabase 오류] {e}")
        return None

def sb_load_tests():
    rows = _sb_request('GET', 'tests', 'select=data&order=created_at.asc')
    if rows is None:
        return []
    return [r['data'] for r in rows]

def sb_save_test(test):
    test_id = test.get('id', '')
    existing = _sb_request('GET', 'tests', f'id=eq.{quote(test_id)}&select=id')
    if existing:
        _sb_request('PATCH', 'tests', f'id=eq.{quote(test_id)}', {'data': test})
    else:
        _sb_request('POST', 'tests', '', {'id': test_id, 'data': test})

def sb_delete_test(test_id):
    _sb_request('DELETE', 'tests', f'id=eq.{quote(test_id)}')

def sb_load_inactive():
    rows = _sb_request('GET', 'app_config', f'key=eq.inactive&select=value')
    if rows and len(rows) > 0:
        return rows[0].get('value', [])
    return []

def sb_save_inactive(data):
    existing = _sb_request('GET', 'app_config', 'key=eq.inactive&select=key')
    if existing:
        _sb_request('PATCH', 'app_config', 'key=eq.inactive', {'value': data})
    else:
        _sb_request('POST', 'app_config', '', {'key': 'inactive', 'value': data})

# ── 로컬 JSON 폴백 ───────────────────────────────

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def local_load_tests():
    path = os.path.join(DATA_DIR, 'tests.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def local_save_tests(tests):
    with open(os.path.join(DATA_DIR, 'tests.json'), 'w', encoding='utf-8') as f:
        json.dump(tests, f, ensure_ascii=False, indent=2)

def local_load_inactive():
    path = os.path.join(DATA_DIR, 'inactive.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def local_save_inactive(data):
    with open(os.path.join(DATA_DIR, 'inactive.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

# ── 통합 인터페이스 ──────────────────────────────

USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

def load_tests():
    return sb_load_tests() if USE_SUPABASE else local_load_tests()

def save_test(test):
    if USE_SUPABASE:
        sb_save_test(test)
    else:
        tests = local_load_tests()
        existing = next((i for i, t in enumerate(tests) if t['id'] == test['id']), None)
        if existing is not None:
            tests[existing] = test
        else:
            tests.append(test)
        local_save_tests(tests)

def delete_test(test_id):
    if USE_SUPABASE:
        sb_delete_test(test_id)
    else:
        tests = [t for t in local_load_tests() if t['id'] != test_id]
        local_save_tests(tests)

def load_inactive():
    return sb_load_inactive() if USE_SUPABASE else local_load_inactive()

def save_inactive(data):
    if USE_SUPABASE:
        sb_save_inactive(data)
    else:
        local_save_inactive(data)

# ── HTTP Handler ──────────────────────────────────

class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/tests':
            self._json_response(load_tests())
        elif parsed.path == '/api/inactive':
            self._json_response(load_inactive())
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/tests':
            body = self._read_body()
            if body is None:
                return
            if not body.get('id'):
                body['id'] = 'custom_' + uuid.uuid4().hex[:10]
            save_test(body)
            self._json_response({'ok': True, 'id': body['id']})
        elif parsed.path == '/api/inactive':
            body = self._read_body()
            if body is None:
                return
            save_inactive(body)
            self._json_response({'ok': True})
        else:
            self._json_response({'error': 'Not found'}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/tests/'):
            test_id = parsed.path.split('/api/tests/')[1]
            delete_test(test_id)
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

    def log_message(self, format, *args):
        if '/api/' in str(args[0]):
            super().log_message(format, *args)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    mode = "Supabase DB" if USE_SUPABASE else "로컬 JSON"
    print(f'서버 시작: http://0.0.0.0:{port} (저장: {mode})')
    server = HTTPServer(('0.0.0.0', port), AppHandler)
    server.serve_forever()
