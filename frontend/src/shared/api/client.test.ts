import { afterEach, describe, expect, it, vi } from 'vitest'
import { createBffClient } from './client'
import type { Operation } from './contracts'

const start = {
  survey_id: 'rheuma_screening_v1',
  weights_version: 'draft-v1',
  disclaimer_version: 'demo-v1',
  disclaimer_accepted: true,
} as const

const operationId = '02995529-91a3-4550-aa71-aa9fe798d274'
const statusUrl = '/api/v1/operations/screening/' + operationId
const receipt = (url = statusUrl) =>
  Response.json({ operation_id: operationId, status_url: url }, { status: 202 })
const status = (state: Operation['state'], error?: Operation['error']) =>
  Response.json({
    operation_id: operationId,
    state,
    resources: [],
    updated_at: '2026-01-01T00:00:00Z',
    error,
  } satisfies Operation)
const pending = () => {}
const signal = new AbortController().signal

afterEach(() => vi.useRealTimers())

describe('BFF client', () => {
  it('keeps the key and body on transport retry and allocates a new key for a new intent', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('Connection reset'))
      .mockResolvedValueOnce(receipt())
      .mockResolvedValueOnce(status('succeeded'))
      .mockResolvedValueOnce(receipt())
      .mockResolvedValueOnce(status('succeeded'))
    const api = createBffClient(fetcher)
    const first = api.start(start)
    await expect(first(signal, pending)).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      retryable: true,
    })
    await first(signal, pending)
    await api.start(start)(signal, pending)

    const posts = fetcher.mock.calls.filter(
      ([path]) => path === '/api/v1/screenings',
    )
    const keys = posts.map(([, init]) =>
      new Headers(init?.headers).get('Idempotency-Key'),
    )
    expect(keys).toHaveLength(3)
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
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(receipt())
      .mockResolvedValueOnce(
        Response.json({ code: 'UNAVAILABLE' }, { status: 503 }),
      )
      .mockResolvedValueOnce(status('pending'))
      .mockResolvedValueOnce(status('succeeded'))
    const task = createBffClient(fetcher).start(start)
    const onPending = vi.fn()
    await expect(task(signal, onPending)).rejects.toMatchObject({
      code: 'UNAVAILABLE',
      retryable: true,
    })
    const completion = expect(task(signal, onPending)).resolves.toMatchObject({
      state: 'succeeded',
    })
    await vi.advanceTimersByTimeAsync(1000)
    await completion
    expect(onPending).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/screenings',
      statusUrl,
      statusUrl,
      statusUrl,
    ])
  })

  it('surfaces the error from a rejected operation', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(receipt())
      .mockResolvedValueOnce(
        status('rejected', {
          code: 'DISCLAIMER_VERSION_MISMATCH',
          message: 'The disclaimer has changed',
        }),
      )
    await expect(
      createBffClient(fetcher).start(start)(signal, pending),
    ).rejects.toMatchObject({
      code: 'DISCLAIMER_VERSION_MISMATCH',
      retryable: false,
    })
  })

  it('surfaces a private resource denial without creating a session', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async () =>
        Response.json({ code: 'SESSION_REQUIRED' }, { status: 401 }),
      )
    await expect(
      createBffClient(fetcher).screening(operationId, signal),
    ).rejects.toMatchObject({ code: 'SESSION_REQUIRED', status: 401 })
    expect(fetcher.mock.calls.map(([p]) => p)).toEqual([
      '/api/v1/screenings/' + operationId,
      '/api/v1/auth/session',
      '/api/v1/auth/session/refresh',
    ])
  })

  it('rotates only once for concurrent expired requests, without creating a guest', async () => {
    let valid = false
    const fetcher = vi.fn<typeof fetch>(async (path) => {
      if (path === '/api/v1/auth/session/refresh') {
        valid = true
        return Response.json({})
      }
      return valid
        ? Response.json({ roles: ['patient'] })
        : Response.json({ code: 'SESSION_REQUIRED' }, { status: 401 })
    })
    const api = createBffClient(fetcher)
    const replies = await Promise.all([
      api.ensureSession()(signal, pending),
      api.ensureSession()(signal, pending),
    ])
    expect(replies.map((v) => v.roles)).toEqual([['patient'], ['patient']])
    expect(
      fetcher.mock.calls.filter(([p]) => p === '/api/v1/auth/session/refresh'),
    ).toHaveLength(1)
    expect(
      fetcher.mock.calls.some(([p]) => p === '/api/v1/auth/guest-sessions'),
    ).toBe(false)
  })

  it('blocks a receipt that would send a browser request outside the BFF', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(receipt('https://example.org' + statusUrl))
    await expect(
      createBffClient(fetcher).start(start)(signal, pending),
    ).rejects.toMatchObject({ code: 'INVALID_BFF_URL' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
