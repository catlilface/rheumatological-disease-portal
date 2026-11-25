"""Exercise the v1 browser contract over a loopback Kubernetes port-forward (stdlib only)."""
import json
import sys
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from uuid import uuid4

origin = sys.argv[1].rstrip('/')
url = urlsplit(origin)
# The cluster port-forward uses HTTP. Only replay this probe's own synthetic
# guest cookie over loopback; real browsers still require Secure cookies and TLS.
if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost'):
    sys.exit('Expected an HTTP port-forward on loopback')
conn = HTTPConnection(url.hostname, url.port, timeout=10)
base = '/api/v1'
session = SimpleCookie()


def request(path, *, method='GET', data=None, status=200):
    headers = {}
    if method == 'POST':
        headers.update({'Origin': origin, 'X-Portal-Request': '1', 'Idempotency-Key': str(uuid4())})
    if session:
        headers['Cookie'] = 'portal_session=' + session['portal_session'].value
    if data is not None:
        headers['Content-Type'] = 'application/json'
    conn.request(method, path, body=json.dumps(data).encode() if data is not None else None, headers=headers)
    response = conn.getresponse()
    body = response.read()
    assert response.status == status, (method, path, response.status)
    return response.headers, body


def get(path):
    return json.loads(request(path)[1])


def command(path, data):
    headers, body = request(path, method='POST', data=data, status=202)
    location = json.loads(body)['status_url']
    assert location == headers['Location'] and location.startswith(base + '/operations/')
    op = get(location)
    assert op['state'] == 'succeeded', op['state']
    return {r['resource_type']: r['resource_id'] for r in op['resources']}


assert get('/health') == {'status': 'ok'}
survey = get(base + '/surveys/rheuma_screening_v1')
assert any(q['code'] == 'В1' for b in survey['blocks'] for q in b['questions'])
headers, _ = request(base + '/auth/guest-sessions', method='POST', status=201)
for cookie in headers.get_all('Set-Cookie'):
    session.load(cookie)
assert session['portal_session']['secure'] and session['portal_session']['httponly']

start = {key: survey[key] for key in ('survey_id', 'weights_version', 'disclaimer_version')}
sid = command(base + '/screenings', dict(start, disclaimer_accepted=True))['screening']
path = base + '/screenings/' + sid
command(path + '/answers', {'expected_session_version': get(path)['version'], 'question_code': 'В1', 'value': True})
result = get(path + '/results')
assert result['red_flag'] and result['score'] is None
ref = {key: result[key] for key in ('result_id', 'version')}
rid = command(base + '/reports', {'kind': 'screening', 'result': ref})['report']
report = get(base + '/reports/' + rid)
assert report['download_url'] == base + '/reports/' + rid + '/pdf'
headers, pdf = request(report['download_url'])
assert headers['Content-Type'] == 'application/pdf' and pdf.startswith(b'%PDF-')
articles = base + '/knowledge-base/articles'
slug = get(articles)['items'][0]['slug']
assert get(articles + '/' + slug)['body_markdown']
conn.close()
print('OK: BFF v1 guest screening, Unicode answer, versioned result, report PDF and content')
