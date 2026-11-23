"""Private license database + bearer-protected administration. Run behind HTTPS."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager


class ServiceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class LicenseStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS licenses (
                  id TEXT PRIMARY KEY, key_hash TEXT UNIQUE NOT NULL, customer TEXT NOT NULL,
                  expires REAL, max_devices INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS devices (
                  license_id TEXT NOT NULL REFERENCES licenses(id), device TEXT NOT NULL,
                  last_seen REAL NOT NULL, PRIMARY KEY(license_id, device));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def create(self, customer, days, seats):
        if not isinstance(customer, str) or not 0 < len(customer.strip()) <= 200:
            raise ServiceError(400, 'Customer required (max 200 characters).')
        if type(seats) is not int or not 1 <= seats <= 100:
            raise ServiceError(400, 'Devices must be 1..100.')
        if days is not None and (type(days) is not int or not 1 <= days <= 36500):
            raise ServiceError(400, 'Days must be 1..36500, or null for lifetime.')
        key, identity = 'AM-' + secrets.token_urlsafe(32), uuid.uuid4().hex
        expires = None if days is None else time.time() + days * 86400
        with self.connect() as db:
            db.execute('INSERT INTO licenses VALUES (?,?,?,?,?,0)',
                       (identity, hashlib.sha256(key.encode()).hexdigest(), customer.strip(), expires, seats))
        return {'id': identity, 'key': key}  # Display once; only the hash is stored.

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT l.id,l.customer,l.expires,l.max_devices,l.revoked,
                    COUNT(d.device) AS used_devices FROM licenses l LEFT JOIN devices d ON l.id=d.license_id
                    GROUP BY l.id ORDER BY l.rowid DESC''')]

    def update(self, identity, values):
        if not values or set(values) - {'revoked', 'add_days', 'max_devices'}:
            raise ServiceError(400, 'Unknown or empty update.')
        if 'revoked' in values and type(values['revoked']) is not bool:
            raise ServiceError(400, 'Revoked must be boolean.')
        if 'add_days' in values and (type(values['add_days']) is not int or not 1 <= values['add_days'] <= 36500):
            raise ServiceError(400, 'Invalid extension.')
        if 'max_devices' in values and (type(values['max_devices']) is not int or not 1 <= values['max_devices'] <= 100):
            raise ServiceError(400, 'Invalid device limit.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM licenses WHERE id=?', (identity,)).fetchone()
            if not row:
                db.rollback()
                raise ServiceError(404, 'License not found.')
            if 'revoked' in values:
                db.execute('UPDATE licenses SET revoked=? WHERE id=?', (int(values['revoked']), identity))
            if 'add_days' in values:
                if row['expires'] is None:
                    db.rollback()
                    raise ServiceError(400, 'Lifetime license does not need extension.')
                db.execute('UPDATE licenses SET expires=? WHERE id=?',
                           (max(time.time(), row['expires']) + values['add_days'] * 86400, identity))
            if 'max_devices' in values:
                used = db.execute('SELECT COUNT(*) FROM devices WHERE license_id=?', (identity,)).fetchone()[0]
                if values['max_devices'] < used:
                    db.rollback()
                    raise ServiceError(409, 'Reset devices before lowering below active device count.')
                db.execute('UPDATE licenses SET max_devices=? WHERE id=?', (values['max_devices'], identity))
            db.commit()
        return {'ok': True}

    def reset_devices(self, identity):
        with self.connect() as db:
            if not db.execute('SELECT id FROM licenses WHERE id=?', (identity,)).fetchone():
                raise ServiceError(404, 'License not found.')
            db.execute('DELETE FROM devices WHERE license_id=?', (identity,))
        return {'ok': True}

    def check(self, key, device):
        if not isinstance(key, str) or not 10 <= len(key) <= 100 or not isinstance(device, str) or not re.fullmatch('[a-f0-9]{64}', device):
            raise ServiceError(400, 'Invalid request.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')  # Seat counting and claiming must be atomic.
            row = db.execute('SELECT * FROM licenses WHERE key_hash=?', (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
            now = time.time()
            if not row or row['revoked'] or (row['expires'] is not None and row['expires'] <= now):
                db.rollback()
                raise ServiceError(401 if not row else 403 if row['revoked'] else 410, 'License unavailable.')
            known = db.execute('SELECT 1 FROM devices WHERE license_id=? AND device=?', (row['id'], device)).fetchone()
            count = db.execute('SELECT COUNT(*) FROM devices WHERE license_id=?', (row['id'],)).fetchone()[0]
            if not known and count >= row['max_devices']:
                db.rollback()
                raise ServiceError(409, 'Device limit reached.')
            db.execute('INSERT INTO devices VALUES (?,?,?) ON CONFLICT(license_id,device) DO UPDATE SET last_seen=excluded.last_seen',
                       (row['id'], device, now))
            db.commit()
            ttl = min(300, max(1, int(row['expires'] - now))) if row['expires'] else 300
            return {'active': True, 'license_id': row['id'], 'ttl': ttl,
                    'expires_at': datetime.fromtimestamp(row['expires'], timezone.utc).isoformat() if row['expires'] else None}


def create_app(db_path, admin_token, trusted_proxy=False):
    if len(admin_token) < 32:
        raise ValueError('Set LICENSE_ADMIN_TOKEN to a random secret of at least 32 characters.')
    store = LicenseStore(db_path)
    limits, lock = {}, threading.Lock()

    def application(environ, start_response):
        status, body, content_type = 200, None, 'application/json; charset=utf-8'
        try:
            path, method = environ.get('PATH_INFO', ''), environ.get('REQUEST_METHOD', 'GET')
            if path == '/admin' and method == 'GET':
                body = Path(__file__).with_name('admin.html').read_bytes()
                content_type = 'text/html; charset=utf-8'
            else:
                if path.startswith('/admin/'):
                    if not hmac.compare_digest(environ.get('HTTP_AUTHORIZATION', ''), 'Bearer ' + admin_token):
                        raise ServiceError(401, 'Unauthorized.')
                elif path == '/v1/check':
                    # One gunicorn worker; use a shared limiter if scaling workers.
                    now = time.monotonic()
                    ip = environ.get('REMOTE_ADDR', '')
                    if trusted_proxy and ip in ('127.0.0.1', '::1'):
                        ip = environ.get('HTTP_X_REAL_IP', ip)
                    with lock:
                        for old in [k for k,v in limits.items() if now-v[0] >= 60]:
                            del limits[old]
                        if len(limits) >= 10000 and ip not in limits:
                            raise ServiceError(429, 'Try later.')
                        since, count = limits.get(ip, (now, 0))
                        limits[ip] = (since, count+1)
                        if count >= 60:
                            raise ServiceError(429, 'Try later.')
                else:
                    raise ServiceError(404, 'Not found.')
                data = {}
                if method in ('POST', 'PATCH'):
                    length = int(environ.get('CONTENT_LENGTH') or 0)
                    if not 0 < length <= 4096:
                        raise ServiceError(400, 'Invalid body size.')
                    data = json.loads(environ['wsgi.input'].read(length))
                    if not isinstance(data, dict):
                        raise ServiceError(400, 'Object required.')
                if path == '/v1/check' and method == 'POST':
                    result = store.check(data.get('key'), data.get('device'))
                elif path == '/admin/licenses' and method == 'GET':
                    result = store.list()
                elif path == '/admin/licenses' and method == 'POST':
                    result = store.create(data.get('customer'), data.get('days'), data.get('max_devices', 1))
                elif re.fullmatch('/admin/licenses/[a-f0-9]{32}', path) and method == 'PATCH':
                    result = store.update(path.split('/')[-1], data)
                elif re.fullmatch('/admin/licenses/[a-f0-9]{32}/devices', path) and method == 'DELETE':
                    result = store.reset_devices(path.split('/')[-2])
                else:
                    raise ServiceError(404, 'Not found.')
                body = json.dumps(result).encode()
        except ServiceError as exc:
            status, body = exc.status, json.dumps({'error': exc.message}).encode()
        except (ValueError, TypeError):
            status, body = 400, b'{"error":"Invalid request."}'
        except Exception:
            status, body = 500, b'{"error":"Service unavailable."}'
        start_response(f'{status} ' + {200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',409:'Conflict',410:'Gone',429:'Too Many Requests',500:'Internal Server Error'}[status],
                       [('Content-Type', content_type), ('Cache-Control', 'no-store'),
                        ('X-Content-Type-Options', 'nosniff'), ('X-Frame-Options', 'DENY'),
                        ('Referrer-Policy', 'no-referrer')])
        return [body]
    return application


def production_app():
    return create_app(os.environ['LICENSE_DB'], os.environ['LICENSE_ADMIN_TOKEN'],
                      trusted_proxy=os.environ.get('LICENSE_TRUST_PROXY') == '1')
