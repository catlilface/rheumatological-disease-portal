"""HTTP → BFF → mTLS IAM contract, on the disposable Compose RPC network."""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
import secrets
import unittest
from uuid import uuid4

from ..main import authority


class BrowserIdentity(unittest.TestCase):
    def request(self, method, path, status, *, data=None, cookie=None, headers=None):
        conn = HTTPConnection('bff', 8000, timeout=8)
        try:
            # Host and Origin match the stand's loopback virtual host. Credentials are synthetic.
            fields = {'Host': 'localhost', 'Origin': 'http://localhost', 'X-Portal-Request': '1',
                      'Idempotency-Key': str(uuid4()), 'Content-Type': 'application/json', **(headers or {})}
            if cookie:
                fields['Cookie'] = 'portal_session=' + cookie
            conn.request(method, '/api/v1' + path, json.dumps(data) if data else None, fields)
            response = conn.getresponse()
            raw = response.read()
            self.assertEqual(response.status, status)
            jar = SimpleCookie()
            for item in response.headers.get_all('Set-Cookie', []):
                jar.load(item)
            return json.loads(raw) if raw else None, jar
        finally:
            conn.close()

    def test_staff_login_does_not_confer_ownership(self):
        iam = authority()
        email, password = f'{uuid4()}@example.test', secrets.token_urlsafe(24)
        iam.provision(email, password, 'admin')
        _, guest = self.request('POST', '/auth/guest-sessions', 201)
        owner_cookie = guest['portal_session'].value
        owner = iam.authenticate(owner_cookie).actor
        start = {'survey_id': 'rheuma_screening_v1', 'weights_version': 'draft-v1',
                 'disclaimer_version': 'demo-v1', 'disclaimer_accepted': True}
        receipt, _ = self.request('POST', '/screenings', 202, data=start, cookie=owner_cookie)
        path = receipt['status_url'].removeprefix('/api/v1')
        self.request('GET', path, 200, cookie=owner_cookie)

        self.request('POST', '/auth/session', 401, data={'email': email, 'password': 'incorrect'})
        principal, staff = self.request('POST', '/auth/session', 200, data={'email': email, 'password': password})
        self.assertEqual((principal['kind'], principal['roles']), ('staff', ['admin']))
        spoof = {'X-User-ID': owner.subject_id, 'X-Subject-ID': owner.subject_id, 'X-Session-ID': owner.session_id}
        self.request('GET', path, 401, headers=spoof)
        self.request('GET', path, 404, cookie=staff['portal_session'].value, headers=spoof)
        self.request('POST', '/screenings', 422, cookie=staff['portal_session'].value,
                     data={**start, 'ownerSubjectId': owner.subject_id})
        self.request('DELETE', '/auth/session', 204, cookie=owner_cookie)
        self.request('GET', path, 401, cookie=owner_cookie, headers=spoof)
