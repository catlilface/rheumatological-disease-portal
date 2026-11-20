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

  for (const route of ['/about', '/documents']) {
    it(`redirects ${route}/ and keeps its query string`, async () => {
      const response = await get(`${route}/?source=test`)
      assert.equal(response.status, 301)
      assert.equal(response.headers.get('location'), `${route}?source=test`)
      await response.body.cancel()

      const destination = await get(`${route}?source=test`)
      assert.equal(destination.status, 200)
      assert.match(
        destination.headers.get('content-type') ?? '',
        /^text\/html\b/,
      )
      await destination.body.cancel()
    })
  }

  it('serves the SPA directly at the root', async () => {
    const response = await get('/')
    assert.equal(response.status, 200)
    assert.match(await response.text(), /<div id="root"><\/div>/)
  })
})
