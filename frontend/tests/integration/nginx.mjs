import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

const baseUrl = process.env.FRONTEND_URL ?? 'http://localhost:8080'
const policySlugs = [
  'personal-info',
  'personal-info-agreement',
  'user-agreement',
  'medical-advices',
  'ai',
  'account-deletion',
  'cookies',
]

function get(path) {
  return fetch(new URL(path, baseUrl), {
    redirect: 'manual',
    signal: AbortSignal.timeout(5_000),
  })
}

describe('nginx', () => {
  for (const slug of policySlugs) {
    it(`serves /policy/${slug} as a PDF`, async () => {
      const response = await get(`/policy/${slug}`)
      assert.equal(response.status, 200)
      assert.match(
        response.headers.get('content-type') ?? '',
        /^application\/pdf\b/,
      )
      const bytes = Buffer.from(await response.arrayBuffer())
      assert.equal(bytes.subarray(0, 5).toString('ascii'), '%PDF-')
    })
  }

  it('serves a policy URL with a trailing slash and a query', async () => {
    const response = await get('/policy/cookies/?source=footer')
    assert.equal(response.status, 200)
    assert.match(
      response.headers.get('content-type') ?? '',
      /^application\/pdf\b/,
    )
    await response.body.cancel()
  })

  it('returns 404 for an unknown policy URL', async () => {
    const response = await get('/policy/missing-policy')
    assert.equal(response.status, 404)
    await response.body.cancel()
  })

  for (const [request, route] of [
    ['/about/', '/about'],
    ['/documents/', '/documents'],
    ['/future/nested/page///', '/future/nested/page'],
    ['/x/', '/x'],
    ['/search/%D1%82%D0%B5%D1%81%D1%82/', '/search/%D1%82%D0%B5%D1%81%D1%82'],
  ]) {
    it(`redirects ${request} and keeps its query string`, async () => {
      const query = '?source=test%2Fvalue&tag=a+b'
      const response = await get(`${request}${query}`)
      assert.equal(response.status, 301)
      assert.equal(response.headers.get('location'), `${route}${query}`)
      await response.body.cancel()

      const destination = await get(`${route}${query}`)
      assert.equal(destination.status, 200)
      assert.match(
        destination.headers.get('content-type') ?? '',
        /^text\/html\b/,
      )
      await destination.body.cancel()
    })
  }

  it('leaves asset requests under the asset location', async () => {
    const response = await get('/assets/missing/')
    assert.equal(response.status, 404)
    await response.body.cancel()
  })

  it('serves the SPA directly at the root', async () => {
    const response = await get('/')
    assert.equal(response.status, 200)
    assert.match(await response.text(), /<div id="root"><\/div>/)
  })
})
