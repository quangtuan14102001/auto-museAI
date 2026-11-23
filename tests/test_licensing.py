import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from core.licensing import LicenseSession, _protect
from license_server.app import LicenseStore, ServiceError, create_app


class LicensingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'licenses.sqlite3'
        self.store = LicenseStore(self.path)
        self.record = self.store.create('Khách thử', 30, 1)
        self.device = 'a' * 64

    def tearDown(self):
        self.temp.cleanup()

    def test_same_machine_reuses_seat_and_key_is_not_stored_in_database(self):
        first = self.store.check(self.record['key'], self.device)
        second = self.store.check(self.record['key'], self.device)
        self.assertEqual(first['license_id'], second['license_id'])
        self.assertEqual(self.store.list()[0]['used_devices'], 1)
        self.assertNotIn(self.record['key'].encode(), self.path.read_bytes())

    def test_atomic_device_limit_under_concurrent_activation(self):
        def claim(device):
            try:
                self.store.check(self.record['key'], device)
                return 200
            except ServiceError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ['a' * 64, 'b' * 64]))
        self.assertCountEqual(results, [200, 409])

    def test_revoke_expire_renew_and_device_reset(self):
        self.store.check(self.record['key'], self.device)
        self.store.update(self.record['id'], {'revoked': True})
        with self.assertRaises(ServiceError) as error:
            self.store.check(self.record['key'], self.device)
        self.assertEqual(error.exception.status, 403)
        self.store.update(self.record['id'], {'revoked': False})
        with self.store.connect() as db:
            db.execute('UPDATE licenses SET expires=?', (time.time()-10,))
        with self.assertRaises(ServiceError) as error:
            self.store.check(self.record['key'], self.device)
        self.assertEqual(error.exception.status, 410)
        self.store.update(self.record['id'], {'add_days': 30})
        self.store.reset_devices(self.record['id'])
        self.assertTrue(self.store.check(self.record['key'], 'b'*64)['active'])

    def test_lifetime_and_short_expiry_lease(self):
        record = self.store.create('Lifetime', None, 2)
        result = self.store.check(record['key'], self.device)
        self.assertIsNone(result['expires_at'])
        with self.store.connect() as db:
            db.execute('UPDATE licenses SET expires=? WHERE id=?', (time.time()+20, self.record['id']))
        self.assertLessEqual(self.store.check(self.record['key'], self.device)['ttl'], 20)

    def test_http_admin_is_protected_and_client_cannot_create_key(self):
        app = create_app(self.path, 's'*40)
        for path, method in [('/admin/licenses', 'GET'), ('/admin/licenses', 'POST'),
                              ('/admin/licenses/'+self.record['id'], 'PATCH')]:
            status = []
            app({'PATH_INFO':path, 'REQUEST_METHOD':method}, lambda s,h:status.append(s))
            self.assertTrue(status[0].startswith('401'))

    def test_http_activation_returns_no_admin_secret_or_key(self):
        app = create_app(self.path, 's'*40)
        payload = json.dumps({'key':self.record['key'], 'device':self.device}).encode()
        status=[]
        output=b''.join(app({'PATH_INFO':'/v1/check','REQUEST_METHOD':'POST','CONTENT_LENGTH':str(len(payload)),
                             'wsgi.input':io.BytesIO(payload)}, lambda s,h:status.append(s)))
        self.assertTrue(status[0].startswith('200'))
        self.assertNotIn(self.record['key'].encode(), output)
        self.assertNotIn(b's'*40, output)

    def test_client_never_redirects_credentials_and_invalidates_on_revocation(self):
        with patch('core.licensing.saved_key', return_value=''):
            session=LicenseSession('https://license.example.com')
        response=MagicMock(status_code=200)
        response.json.return_value={'active':True,'ttl':300,'license_id':'test','expires_at':None}
        with patch('core.licensing.device_id', return_value=self.device), patch('core.licensing.save_key'), \
             patch('core.licensing.requests.post', return_value=response) as post:
            session.check(self.record['key'])
            self.assertTrue(session.valid)
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            response.status_code=403
            with self.assertRaisesRegex(ValueError, 'khóa'):
                session.check()
            self.assertFalse(session.valid)

    def test_unconfigured_source_and_corrupt_response_fail_closed(self):
        with patch('core.licensing.saved_key', return_value=''):
            session=LicenseSession('')
        with patch('core.licensing.requests.post') as post:
            with self.assertRaises(ValueError): session.check('AM-example')
            post.assert_not_called()
        session.url='https://license.example.com'
        response=MagicMock(status_code=200)
        response.json.return_value={'active':True,'ttl':99999}
        with patch('core.licensing.device_id', return_value=self.device), patch('core.licensing.requests.post', return_value=response):
            with self.assertRaises(ValueError): session.check('AM-example')
        self.assertFalse(session.valid)

    def test_windows_dpapi_roundtrip(self):
        data=b'AM-private-license-test'
        protected=_protect(data)
        self.assertNotIn(data, protected)
        self.assertEqual(_protect(protected, decrypt=True), data)

    def test_admin_http_create_revoke_and_client_denial(self):
        app = create_app(self.path, 's'*40)
        def call(path, method, payload, admin=False):
            content=json.dumps(payload).encode()
            statuses=[]
            body=b''.join(app({'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(content)),
                               'wsgi.input':io.BytesIO(content),'REMOTE_ADDR':'127.0.0.1',
                               'HTTP_AUTHORIZATION':'Bearer '+'s'*40 if admin else ''},
                              lambda s,h:statuses.append(s)))
            return int(statuses[0].split()[0]), json.loads(body)
        status, record=call('/admin/licenses','POST',{'customer':'Paid customer','days':365,'max_devices':1},True)
        self.assertEqual(status,200)
        self.assertEqual(call('/v1/check','POST',{'key':record['key'],'device':self.device})[0],200)
        self.assertEqual(call('/admin/licenses/'+record['id'],'PATCH',{'revoked':True},True)[0],200)
        self.assertEqual(call('/v1/check','POST',{'key':record['key'],'device':self.device})[0],403)


if __name__ == '__main__':
    unittest.main()
