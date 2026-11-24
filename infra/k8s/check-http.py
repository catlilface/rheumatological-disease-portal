"""Check the current BFF fixture API over a real Kubernetes port-forward (stdlib only)."""
import json
import sys
from urllib.request import Request, urlopen

base = sys.argv[1]


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(base + path, data=data, headers={'Content-Type': 'application/json'}), timeout=10) as response:
        return response.status, response.headers, response.read()


assert json.loads(request('/health')[2]) == {'status': 'ok'}
status, _, body = request('/api/v1/screenings', {'survey_id': 'rheuma_screening_v1'})
assert status == 201
session = json.loads(body)
assert session['survey']['blocks'][1]['questions'][0]['code'] == 'В1'
identifier = session['id']
answer = {'question_code': 'В1', 'value': True}
assert json.loads(request(f'/api/v1/screenings/{identifier}/answers', answer)[2])['answer'] == answer
result = json.loads(request(f'/api/v1/screenings/{identifier}/results')[2])
assert 'mock' in result['disclaimer'].lower() # This is NOT a clinical CQRS result.
_, headers, pdf = request(f'/api/v1/screenings/{identifier}/pdf')
assert headers['Content-Type'] == 'application/pdf' and pdf.startswith(b'%PDF-1.')
articles = json.loads(request('/api/v1/knowledge-base/articles')[2])
assert articles['items']
assert json.loads(request('/api/v1/knowledge-base/articles/' + articles['items'][0]['slug'])[2])['body']
print('OK: BFF HTTP via Kubernetes Service/port-forward, Unicode, fixture result, PDF and content')
