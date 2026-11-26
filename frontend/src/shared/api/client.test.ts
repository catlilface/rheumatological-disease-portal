import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockBff } from '../../../mocks/bff'
import { survey } from '../../../mocks/fixtures'
import { mockBrowserFetch } from '../../../mocks/browser-fetch'
import { createBffClient } from './client'

const start = {
  survey_id: survey.survey_id,
  weights_version: survey.weights_version,
  disclaimer_version: survey.disclaimer_version,
  disclaimer_accepted: true,
} as const

const pending = () => {}
const signal = new AbortController().signal

afterEach(() => vi.useRealTimers())

describe('BFF client', () => {
  it('keeps the key and body on transport retry and allocates a new key for a new intent', async () => {
    const server = mockBrowserFetch(createMockBff({ pendingPolls: 0 }))
    let lostResponse = false
    const fetcher = vi.fn<typeof fetch>(async (path, init) => {
      const response = await server(path, init)
      if (path === '/api/v1/screenings' && !lostResponse) {
        lostResponse = true
        throw new TypeError('Connection reset after BFF accepted the command')
      }
      return response
    })
    const api = createBffClient(fetcher)
    await api.ensureSession()(signal, pending)
    const first = api.start(start)
    await expect(first(signal, pending)).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      retryable: true,
    })
    const result = await first(signal, pending)
    const other = await api.start(start)(signal, pending)
    expect(result.resources[0].resource_id).not.toBe(
      other.resources[0].resource_id,
    )
    const posts = fetcher.mock.calls.filter(
      ([path]) => path === '/api/v1/screenings',
    )
    const keys = posts.map(([, init]) =>
      new Headers(init?.headers).get('Idempotency-Key'),
    )
    expect(keys[0]).toBeTruthy()
    expect(keys[0]).toBe(keys[1])
    expect(keys[1]).not.toBe(keys[2])
    expect(posts[0][1]?.body).toBe(posts[1][1]?.body)
    expect(posts[0][1]).toMatchObject({
      credentials: 'include',
      redirect: 'error',
    })
    expect(new Headers(posts[0][1]?.headers).get('X-Portal-Request')).toBe('1')
  })

  it('polls pending operations and retries polling without resending an accepted command', async () => {
    vi.useFakeTimers()
    const server = mockBrowserFetch()
    let brokenPoll = true
    const fetcher = vi.fn<typeof fetch>(async (path, init) => {
      if (String(path).includes('/operations/') && brokenPoll) {
        brokenPoll = false
        return Response.json({ code: 'UNAVAILABLE' }, { status: 503 })
      }
      return server(path, init)
    })
    const api = createBffClient(fetcher)
    await api.ensureSession()(signal, pending)
    const task = api.start(start)
    const onPending = vi.fn()
    await expect(task(signal, onPending)).rejects.toMatchObject({
      code: 'UNAVAILABLE',
      retryable: true,
    })
    const result = task(signal, onPending)
    const completion = expect(result).resolves.toMatchObject({
      state: 'succeeded',
    })
    await vi.advanceTimersByTimeAsync(1000)
    await completion
    expect(onPending).toHaveBeenCalledTimes(2)
    expect(
      fetcher.mock.calls.filter(([path]) => path === '/api/v1/screenings'),
    ).toHaveLength(1)
  })

  it('surfaces terminal operation errors and preserves private resource scope', async () => {
    const api = createBffClient(
      mockBrowserFetch(createMockBff({ pendingPolls: 0 })),
    )
    const unrelated = createBffClient(mockBrowserFetch())
    await api.ensureSession()(signal, pending)
    await expect(
      api.start({ ...start, disclaimer_version: 'stale' })(signal, pending),
    ).rejects.toMatchObject({
      code: 'DISCLAIMER_VERSION_MISMATCH',
      retryable: false,
    })
    const operation = await api.start(start)(signal, pending)
    await expect(
      unrelated.screening(operation.resources[0].resource_id, signal),
    ).rejects.toMatchObject({ code: 'SESSION_REQUIRED', status: 401 })
  })

  it('blocks a receipt that would send a browser request outside the BFF', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        {
          operation_id: 'a',
          status_url: 'https://example.org/api/v1/operations/screening/a',
        },
        { status: 202 },
      ),
    )
    await expect(
      createBffClient(fetcher).start(start)(signal, pending),
    ).rejects.toMatchObject({ code: 'INVALID_BFF_URL' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
