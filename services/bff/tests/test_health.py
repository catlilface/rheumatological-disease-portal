import pytest

pytestmark = pytest.mark.anyio


async def test_health_returns_ok_without_database(client):
    response = await client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


@pytest.mark.parametrize('path', [
    '/', '/docs', '/redoc', '/openapi.json',
    '/api/v2/auth/medical-data-policy',
    '/api/v1/screenings/not-a-uuid/pdf',
])
async def test_other_endpoints_are_unavailable(client, path):
    assert (await client.get(path)).status_code == 404
