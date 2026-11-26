"""HTTP → BFF → mTLS IAM contract, on the disposable Compose RPC network."""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
import secrets
import unittest
from uuid import uuid4

from .fixtures import staff_fixture
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
            if response.headers.get_content_type() == 'application/pdf':
                return raw, jar
            return json.loads(raw) if raw else None, jar
        finally:
            conn.close()

    def test_guest_registration_reports_existing_account(self):
        registration = {'email': f'{uuid4()}@example.test', 'password': secrets.token_urlsafe(18),
                        'medical_data_consent': {'version': 'demo-medical-v1', 'accepted': True}}
        self.request('POST', '/auth/registrations', 201, data=registration)
        _, guest = self.request('POST', '/auth/guest-sessions', 201)
        cookie = guest['portal_session'].value
        error, _ = self.request('POST', '/auth/registrations', 409, data=registration, cookie=cookie)
        self.assertEqual(error['code'], 'ACCOUNT_ALREADY_EXISTS')
        self.assertEqual(self.request('GET', '/auth/session', 200, cookie=cookie)[0]['kind'], 'guest')

    def test_consent_withdrawal_applies_to_all_patient_sessions(self):
        account = {'email': f'{uuid4()}@example.test', 'password': secrets.token_urlsafe(18)}
        _, first = self.request('POST', '/auth/registrations', 201, data={**account, 'medical_data_consent': {'version': 'demo-medical-v1', 'accepted': True}})
        _, second = self.request('POST', '/auth/session', 200, data=account)
        self.request('GET', '/me/onboarding', 200, cookie=second['portal_session'].value)
        spec = {'kind': 'doctor', 'from_date': '2026-01-01', 'to_date': '2026-01-02', 'sections': ['diary']}
        receipt, _ = self.request('POST', '/reports', 202, data=spec, cookie=second['portal_session'].value)
        op, _ = self.request('GET', receipt['status_url'].removeprefix('/api/v1'), 200, cookie=second['portal_session'].value)
        report = '/reports/' + op['resources'][0]['resource_id']
        self.assertEqual(self.request('GET', report, 200, cookie=second['portal_session'].value)[0]['specification'], spec)
        self.assertTrue(self.request('GET', report + '/pdf', 200, cookie=second['portal_session'].value)[0].startswith(b'%PDF-'))
        for _ in range(2):
            self.request('DELETE', '/me/medical-data-consent', 204, cookie=first['portal_session'].value)
        _, new_login = self.request('POST', '/auth/session', 200, data=account)
        for jar in (first, second, new_login):
            error, _ = self.request('GET', '/me/onboarding', 403, cookie=jar['portal_session'].value)
            self.assertEqual(error['code'], 'CONSENT_REQUIRED')
            self.request('GET', report + '/pdf', 403, cookie=jar['portal_session'].value)
            self.request('POST', '/reports', 403, data=spec, cookie=jar['portal_session'].value)

    def test_patient_journey(self):
        account = {'email': f'{uuid4()}@example.test', 'password': secrets.token_urlsafe(18)}
        registration = {**account, 'medical_data_consent': {'version': 'demo-medical-v1', 'accepted': True}}
        self.request('POST', '/auth/registrations', 422, data={**registration, 'role': 'admin'})
        principal, jar = self.request('POST', '/auth/registrations', 201, data=registration)
        self.assertEqual(principal['roles'], ['patient'])
        session = jar['portal_session'].value
        self.request('PUT', '/admin/account-role', 403, cookie=session, data={'email': account['email'], 'role': 'admin'})
        profile = {'name': 'Тест', 'diagnosis': None, 'medications': [], 'reminders': {'timezone': 'UTC', 'enabled': False, 'channels': []}}
        self.request('PUT', '/me/onboarding', 202, cookie=session, data=profile)
        _, rotated = self.request('POST', '/auth/session/refresh', 200, headers={'Cookie': 'portal_refresh=' + jar['portal_refresh'].value})
        self.request('GET', '/me/onboarding', 401, cookie=session)
        current = rotated['portal_session'].value
        self.assertEqual(self.request('GET', '/me/onboarding', 200, cookie=current)[0]['name'], 'Тест')
        self.assertEqual(self.request('GET', '/me/screening-results', 200, cookie=current)[0]['total'], 0)
        survey, _ = self.request('GET', '/surveys/rheuma_screening_v1', 200)
        start = {k: survey[k] for k in ('survey_id', 'weights_version', 'disclaimer_version')}
        receipt, _ = self.request('POST', '/screenings', 202, cookie=current, data={**start, 'disclaimer_accepted': True})
        operation, _ = self.request('GET', receipt['status_url'].removeprefix('/api/v1'), 200, cookie=current)
        path = '/screenings/' + operation['resources'][0]['resource_id']
        self.request('POST', path + '/answers', 202, cookie=current, data={'expected_session_version': 1, 'question_code': 'В1', 'value': True})
        result, _ = self.request('GET', path + '/results', 200, cookie=current)
        exact = '/results/' + result['result_id'] + '/versions/' + str(result['version'])
        other, other_jar = self.request('POST', '/auth/registrations', 201, data={**registration, 'email': f'{uuid4()}@example.test'})
        self.assertEqual(other['roles'], ['patient'])
        stranger = other_jar['portal_session'].value
        _, guest = self.request('POST', '/auth/guest-sessions', 201)
        self.request('GET', '/me/onboarding', 403, cookie=guest['portal_session'].value)
        self.request('DELETE', '/auth/session', 204, cookie=current)
        _, login = self.request('POST', '/auth/session', 200, data=account)
        cookie = login['portal_session'].value
        self.assertEqual(self.request('GET', '/me/onboarding', 200, cookie=cookie)[0]['name'], 'Тест')
        self.assertEqual(self.request('GET', '/me/screening-results', 200, cookie=cookie)[0]['items'], [result])
        self.assertEqual(self.request('GET', exact, 200, cookie=cookie)[0], result)
        self.request('GET', exact, 404, cookie=stranger)
        explanation = exact + '/explanation'
        self.assertEqual(self.request('GET', explanation, 404, cookie=cookie)[0]['code'], 'EXPLANATION_NOT_READY')
        self.request('POST', explanation, 202, cookie=cookie)
        self.assertEqual(self.request('GET', explanation, 200, cookie=cookie)[0]['result']['result_id'], result['result_id'])
        self.request('GET', explanation, 404, cookie=stranger)
        self.assertEqual(self.request('GET', '/me/screening-results', 200, cookie=stranger)[0]['items'], [])
        admin_email = f'{uuid4()}@example.test'
        staff_fixture(authority(), admin_email, account['password'], 'admin')
        _, admin = self.request('POST', '/auth/session', 200, data={**account, 'email': admin_email})
        self.request('PUT', '/admin/account-role', 204, cookie=admin['portal_session'].value, data={'email': account['email'], 'role': 'editor'})
        self.request('GET', '/me/onboarding', 401, cookie=cookie)
        editor, jar = self.request('POST', '/auth/session', 200, data=account)
        self.assertEqual(editor['roles'], ['editor'])
        self.request('GET', exact, 404, cookie=jar['portal_session'].value)

    def test_staff_login_does_not_confer_ownership(self):
        iam = authority()
        email, password = f'{uuid4()}@example.test', secrets.token_urlsafe(24)
        staff_fixture(iam, email, password, 'admin')
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
