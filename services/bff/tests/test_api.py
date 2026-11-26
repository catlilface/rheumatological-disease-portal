"""Browser contract tests for an isolated Go BFF process."""
import re
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import yaml
from jsonschema import Draft202012Validator

pytestmark = pytest.mark.anyio
BASE = '/api/v1'


@pytest.fixture(scope='session')
def contract():
    root = Path(__file__).resolve().parents[3] / 'contracts/http'
    spec = yaml.safe_load((root / 'bff-v1.openapi.yaml').read_text())
    assert spec['servers'] == [{'url': BASE}]
    defs = yaml.safe_load((root / 'schemas.yaml').read_text())['$defs']
    return spec, defs


@pytest.fixture
async def api(server, contract):
    url, context = server

    async def key(request):
        request.headers.setdefault('Idempotency-Key', str(uuid4()))

    spec, defs = contract
    paths = [(re.compile(re.sub(r'\{[^}]+\}', '[^/]+', BASE + path)), ops) for path, ops in spec['paths'].items()]

    async def check_response(response):
        request = response.request
        op = next(ops[request.method.lower()] for pattern, ops in paths if pattern.fullmatch(request.url.path))
        statuses = op['responses']
        assert str(response.status_code) in statuses, (op['operationId'], response.status_code)
        schema = statuses[str(response.status_code)]
        if '$ref' in schema:
            schema = spec['components']['responses'][schema['$ref'].split('/')[-1]]
        for name, header in schema.get('headers', {}).items():
            if header.get('required'):
                assert name in response.headers
        raw = await response.aread()
        if 'content' not in schema:
            assert not raw
            return
        mime = response.headers['content-type'].split(';')[0]
        media = schema['content'][mime]
        if mime == 'application/json':
            name = media['schema']['$ref'].split('/')[-1]
            Draft202012Validator({'$defs': defs, '$ref': f'#/$defs/{name}'},
                                 format_checker=Draft202012Validator.FORMAT_CHECKER).validate(response.json())
        elif mime == 'text/plain':
            assert response.status_code == 400 and raw.strip() == b'Invalid host header'
        else:
            assert mime == 'application/pdf' and raw.startswith(b'%PDF-')

    async with httpx.AsyncClient(verify=context, trust_env=False, base_url=url,
                                headers={'Origin': url, 'X-Portal-Request': '1'},
                                event_hooks={'request': [key], 'response': [check_response]}) as client:
        yield client


async def command(api, method, path, **kw):
    r = await api.request(method, BASE + path, **kw)
    assert r.status_code == 202, r.text
    assert r.headers['location'] == r.json()['status_url']
    op = (await api.get(r.headers['location'])).json()
    assert op['operation_id'] == r.json()['operation_id']
    return op


async def success(api, method, path, **kw):
    op = await command(api, method, path, **kw)
    assert op['state'] == 'succeeded', op
    return {r['resource_type']: r['resource_id'] for r in op['resources']}


def test_each_operation_has_one_documentation_section(contract):
    spec, _ = contract
    declared = [tag['name'] for tag in spec.get('tags', [])]
    assert len(set(declared)) == len(declared)
    used = set()
    for path in spec['paths'].values():
        for method, op in path.items():
            if method == 'parameters':
                continue
            tags = op.get('tags', [])
            assert len(tags) == 1 and tags[0] in declared, op['operationId']
            used.add(tags[0])
    assert used == set(declared)


async def test_contract_inventory(api, contract):
    # Each documented method must reach its handler, even without a session. The
    # response hook rejects a mux-level plain-text 404/405 or an invalid envelope.
    spec, _ = contract
    for path, methods in spec['paths'].items():
        path = re.sub(r'\{[^}]+\}', str(uuid4()), path)
        for method in methods.keys() - {'parameters'}:
            await api.request(method, BASE + path)


async def test_screening_result_and_explanation_are_linked(api):
    survey = (await api.get(BASE + '/surveys/rheuma_screening_v1')).json()
    assert {b['code'] for b in survey['blocks']} >= set(survey['scoring']['sum_blocks'])
    await api.post(BASE + '/auth/guest-sessions')
    start = {k: survey[k] for k in ('survey_id', 'weights_version', 'disclaimer_version')}
    start['disclaimer_accepted'] = True
    ids = await success(api, 'POST', '/screenings', json=start)
    path = '/screenings/' + ids['screening']
    assert (await api.get(BASE + path + '/results')).status_code == 409
    a = {'question_code': 'В1', 'value': True, 'expected_session_version': 1}
    headers = {'Idempotency-Key': str(uuid4())}
    op = await command(api, 'POST', path + '/answers', json=a, headers=headers)
    assert op == await command(api, 'POST', path + '/answers', json=a, headers=headers)
    assert (await api.post(BASE + path + '/answers', json=dict(a, value=False), headers=headers)).status_code == 409
    session = (await api.get(BASE + path)).json()
    assert session['interrupted_by_red_flag'] and session['version'] == 2
    rp = '/results/{result_id}/versions/{version}'.format(**session['result'])
    early = (await api.get(BASE + rp)).json()
    assert early['red_flag_codes'] == ['В1'] and early['score'] is None
    await success(api, 'POST', path + '/continuations', json={'expected_session_version': 2})
    version = 3
    for block in survey['blocks']:
        for q in block['questions']:
            a = {'question_code': q['code'], 'value': q['options'][0]['value'] if q['type'] == 'single_choice' else False,
                 'expected_session_version': version}
            await success(api, 'POST', path + '/answers', json=a)
            version += 1
    await success(api, 'POST', path + '/completions', json={'expected_session_version': version})
    result = (await api.get(BASE + path + '/results')).json()
    assert result['result_id'] == early['result_id'] and result['version'] > early['version']
    assert result['risk_level'] == 'red_flag' and result['score'] == 0
    assert (await api.get(BASE + rp)).json() == early
    await success(api, 'POST', rp + '/explanation')
    explanation = (await api.get(BASE + rp + '/explanation')).json()
    assert explanation['result'] == session['result']
    source = explanation['sources'][0]
    assert (await api.get(BASE + '/knowledge-base/articles/' + source['slug'])).json()['version'] == source['version']
    articles = (await api.get(BASE + '/knowledge-base/articles?section=diseases&disease_tag=SPA')).json()
    assert articles['total'] == 1 and articles['items'][0]['disease_tag'] == 'SPA'
    assert (await api.get(BASE + '/doctor-route')).json()['sources']


async def register(api, email='patient@example.test'):
    policy = (await api.get(BASE + '/auth/medical-data-policy')).json()
    body = {'email': email, 'password': 'synthetic-password', 'medical_data_consent': {'accepted': True, 'version': policy['version']}}
    assert (await api.post(BASE + '/auth/registrations', json=body)).status_code == 201
    return {'email': email, 'password': body['password']}


async def test_cabinet_links_and_mutations(api):
    from datetime import UTC, datetime
    await register(api)
    api.headers['X-Portal-Session'] = (await api.get(BASE + '/auth/session')).json()['session_id']
    today = datetime.now(UTC).date().isoformat()
    med = {'name': 'Демо', 'dose_text': 'Тест', 'local_times': ['08:00'], 'starts_on': today}
    prefs = {'enabled': True, 'timezone': 'UTC', 'channels': ['email']}
    await success(api, 'PUT', '/me/onboarding', json={'diagnosis': None, 'medications': [med], 'reminders': prefs})
    meds = (await api.get(BASE + '/me/medications')).json()['items']
    assert (await api.get(BASE + '/me/onboarding')).json()['medications'] == meds
    assert (await api.get(BASE + '/me/reminder-settings')).json() == prefs
    slot = (await api.get(BASE + '/me/doses', params={'from_date': today, 'to_date': today})).json()['items'][0]
    assert slot['medication_id'] == meds[0]['medication_id']
    await success(api, 'PUT', '/me/doses/' + slot['dose_id'] + '/intake', json={'status': 'missed'})
    assert (await api.get(BASE + '/me/doses?status=missed&from_date=' + today + '&to_date=' + today)).json()['total'] == 1
    note = (await api.get(BASE + '/me/notifications?unread=true')).json()['items'][0]
    assert note['dose_id'] == slot['dose_id'] and note['channel'] == 'in_app'
    await success(api, 'PUT', '/me/notifications/' + note['notification_id'] + '/read')
    assert (await api.get(BASE + '/me/notifications?unread=true')).json()['total'] == 0
    data = {'entry_date': today, 'pain_vas': 2, 'stiffness_minutes': 3, 'swollen_joint_count': 0,
            'tender_joint_count': 1, 'fatigue': 3, 'flare': False}
    ids = await success(api, 'POST', '/me/diary-entries', json=data)
    path = '/me/diary-entries/' + ids['diary_entry']
    await success(api, 'PUT', path, json=dict(data, fatigue=5))
    assert (await api.get(BASE + path)).json() == (await api.get(BASE + '/me/diary-entries')).json()['items'][0]
    await success(api, 'DELETE', path)
    assert (await api.get(BASE + path)).status_code == 404
    await success(api, 'PUT', '/me/reminder-settings', json=dict(prefs, enabled=False))
    new = await success(api, 'POST', '/me/medications', json=dict(med, name='Новое'))
    med_path = '/me/medications/' + new['medication']
    await success(api, 'PUT', med_path, json=dict(med, local_times=['09:00']))
    await success(api, 'DELETE', med_path)
    assert (await api.get(BASE + '/me/notifications')).json()['total'] == 1


async def test_doctor_report_and_revocable_link(api):
    from datetime import datetime, timedelta
    await register(api)
    spec = {'kind': 'doctor', 'from_date': '2026-01-01', 'to_date': '2026-01-31', 'sections': ['diary']}
    ids = await success(api, 'POST', '/reports', json=spec)
    path = '/reports/' + ids['report']
    report = (await api.get(BASE + path)).json()
    assert report['specification'] == spec and report['status'] == 'ready'
    assert report['download_url'] == BASE + path + '/pdf'
    pdf = await api.get(report['download_url'])
    assert pdf.headers['content-type'] == 'application/pdf' and pdf.content.startswith(b'%PDF-')
    shares = path + '/shares'
    ids = await success(api, 'POST', shares)
    link_path = shares + '/' + ids['share']
    share = (await api.get(BASE + link_path)).json()
    assert share['report_id'] == report['report_id']
    assert datetime.fromisoformat(share['expires_at']) - datetime.fromisoformat(share['issued_at']) == timedelta(days=1)
    token = {'token': share['url'].split('#')[1]}
    assert (await api.post(BASE + '/shared-reports/download', json=token)).content == pdf.content
    # Exact expiry with an injected clock is covered by Go's TestGrantExpiry.
    await success(api, 'DELETE', link_path)
    assert (await api.post(BASE + '/shared-reports/download', json=token)).status_code == 410
    ids = await success(api, 'POST', shares)
    link = (await api.get(BASE + shares + '/' + ids['share'])).json()
    session = (await api.get(BASE + '/auth/session')).json()['session_id']
    assert (await api.delete(BASE + '/me/medical-data-consent', headers={'X-Portal-Session': session})).status_code == 204
    assert (await api.get(report['download_url'])).status_code == 403
    assert (await api.post(BASE + '/shared-reports/download', json={'token': link['url'].split('#')[1]})).status_code == 410


async def test_moderation_visibility(api):
    await register(api)
    ids = await success(api, 'POST', '/community/topics', json={'title': 'Demo topic', 'body': 'Synthetic example'})
    path = '/community/topics/' + ids['topic']
    assert (await api.get(BASE + path)).status_code == 404
    assert (await api.get(BASE + '/moderation/cases')).status_code == 403
    login = {'email': 'moderator@example.test', 'password': 'demo-moderator'}
    assert (await api.post(BASE + '/auth/session', json=login)).status_code == 200
    case = (await api.get(BASE + '/moderation/cases')).json()['items'][0]
    assert case['target'] == {'kind': 'topic', 'id': ids['topic']}
    await success(api, 'PUT', '/moderation/cases/' + case['case_id'] + '/decision',
                  json={'action': 'approve', 'reason': 'Demo', 'expected_version': case['version']})
    assert (await api.get(BASE + path)).json()['body'] == 'Synthetic example'
    assert (await api.get(BASE + '/moderation/cases')).json()['total'] == 0
    assert ids['topic'] in {t['topic_id'] for t in (await api.get(BASE + '/community/topics')).json()['items']}
    post = await success(api, 'POST', path + '/posts', json={'body': 'Тестовый ответ'})
    assert (await api.get(BASE + path + '/posts')).json()['total'] == 0

    async def decide(case_id, action):
        await success(api, 'PUT', '/moderation/cases/' + case_id + '/decision',
                      json={'action': action, 'reason': 'Мок', 'expected_version': 1})
    await decide(post['case'], 'approve')
    assert (await api.get(BASE + path + '/posts')).json()['items'][0]['post_id'] == post['post']
    flag = await success(api, 'POST', '/community/flags', json={'target': {'kind': 'topic', 'id': ids['topic']}, 'reason': 'Тест'})
    await decide(flag['case'], 'hide')
    assert (await api.get(BASE + path + '/posts')).status_code == 404


async def test_isolation_and_closed_screening(api):
    await api.post(BASE + '/auth/guest-sessions')
    start = {'survey_id': 'rheuma_screening_v1', 'weights_version': 'draft-v1', 'disclaimer_version': 'demo-v1',
             'disclaimer_accepted': True}
    assert (await api.post(BASE + '/screenings', json=dict(start, disclaimer_accepted=False))).status_code == 422
    op = await command(api, 'POST', '/screenings', json=start)
    path = '/screenings/' + op['resources'][0]['resource_id']
    rejected = await command(api, 'POST', path + '/answers',
                             json={'question_code': 'A1', 'value': 'true', 'expected_session_version': 1})
    assert rejected['error']['code'] == 'INVALID_ANSWER'
    rejected = await command(api, 'POST', path + '/completions', json={'expected_session_version': 1})
    assert rejected['error']['code'] == 'REQUIRED_ANSWERS_MISSING'
    rejected = await command(api, 'POST', path + '/abandonments', json={'expected_session_version': 2})
    assert rejected['error']['code'] == 'SESSION_VERSION_CONFLICT'
    await success(api, 'POST', path + '/abandonments', json={'expected_session_version': 1})
    assert (await api.get(BASE + path)).json()['status'] == 'abandoned'
    api.cookies.clear()
    await api.post(BASE + '/auth/guest-sessions')
    assert (await api.get(BASE + path)).status_code == 404
    assert (await api.get(BASE + '/operations/screening/' + op['operation_id'])).status_code == 404


@pytest.mark.parametrize(('points', 'level'), [(0, 'low'), (4, 'low'), (5, 'medium'), (10, 'medium'), (11, 'high')])
async def test_demo_thresholds(api, points, level):
    await api.post(BASE + '/auth/guest-sessions')
    start = {'survey_id': 'rheuma_screening_v1', 'weights_version': 'draft-v1', 'disclaimer_version': 'demo-v1',
             'disclaimer_accepted': True}
    id = (await success(api, 'POST', '/screenings', json=start))['screening']
    answers = {'A1': points in (5, 11), 'A6': 'gt60' if points >= 10 else 'lt30',
               'Б1': points >= 4, 'Г1': points >= 10, 'В1': False}
    path = '/screenings/' + id
    for version, (code, value) in enumerate(answers.items(), 1):
        await success(api, 'POST', path + '/answers', json={'expected_session_version': version, 'question_code': code, 'value': value})
    await success(api, 'POST', path + '/completions', json={'expected_session_version': 6})
    result = (await api.get(BASE + path + '/results')).json()
    assert result['score'] == sum(result['block_scores'].values()) == points
    assert result['risk_level'] == level and not result['red_flag']
    spec = {'kind': 'screening', 'result': {'result_id': result['result_id'], 'version': result['version']}}
    rid = (await success(api, 'POST', '/reports', json=spec))['report']
    assert (await api.get(BASE + '/reports/' + rid)).json()['specification'] == spec


async def test_invalid_host_is_a_plain_text_400(api):
    response = await api.get(BASE + '/auth/medical-data-policy', headers={'Host': 'invalid.test'})
    assert response.status_code == 400


async def test_invalid_json_and_contract_fields(api):
    path = BASE + '/auth/registrations'
    malformed = await api.post(path, content=b'{', headers={'Content-Type': 'application/json'})
    assert malformed.status_code == 400 and malformed.json()['code'] == 'INVALID_JSON'
    body = {'email': 'demo@example.test', 'password': 'demo',
            'medical_data_consent': {'version': 'demo-medical-v1', 'accepted': True}}
    for invalid in [dict(body, roles=['moderator']), dict(body, medical_data_consent=None),
                    dict(body, medical_data_consent=dict(body['medical_data_consent'], accepted='true'))]:
        response = await api.post(path, json=invalid)
        assert response.status_code == 422 and response.json()['code'] == 'VALIDATION_ERROR'


async def test_sessions_and_guards(api):
    assert (await api.get(BASE + '/auth/session')).status_code == 401
    bad = await api.post(BASE + '/auth/guest-sessions', headers={'Origin': 'https://untrusted.test'})
    assert bad.status_code == 403
    r = await api.post(BASE + '/auth/guest-sessions')
    assert r.status_code == 201 and r.json()['kind'] == 'guest'
    assert 'no-store' in r.headers['cache-control']
    old_refresh = api.cookies['portal_refresh']
    key = {'Idempotency-Key': str(uuid4())}
    assert (await api.post(BASE + '/auth/session/refresh', headers=key)).status_code == 200
    rotated = api.cookies['portal_refresh']
    assert rotated != old_refresh
    replay = await api.post(BASE + '/auth/session/refresh', headers={**key, 'Cookie': 'portal_refresh=' + old_refresh})
    assert replay.status_code == 401
    assert (await api.get(BASE + '/auth/session')).status_code == 401
    assert (await api.post(BASE + '/auth/guest-sessions')).status_code == 201
    assert (await api.get(BASE + '/auth/session')).json()['kind'] == 'guest'
    assert (await api.get(BASE + '/me/onboarding')).status_code == 403
    assert (await api.delete(BASE + '/auth/session')).status_code == 204
    assert (await api.get(BASE + '/auth/session')).status_code == 401
