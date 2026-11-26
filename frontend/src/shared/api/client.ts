import type {
  Answer,
  Article,
  ArticlePage,
  Explanation,
  Material,
  Operation,
  Principal,
  Receipt,
  Result,
  ResultRef,
  Revision,
  Screening,
  Start,
  Survey,
} from './contracts'

const prefix = '/api/v1'
const segment = encodeURIComponent
const resultPath = ({ result_id, version }: ResultRef) =>
  '/results/' + segment(result_id) + '/versions/' + segment(String(version))
const screeningPath = (id: string) => '/screenings/' + segment(id)

export class BffError extends Error {
  readonly code: string
  readonly status: number
  readonly retryable: boolean

  constructor(
    code: string,
    status = 0,
    retryable = status === 0 || status === 429 || status >= 500,
  ) {
    super(code)
    this.code = code
    this.status = status
    this.retryable = retryable
  }
}

export type Command<T> = (
  signal: AbortSignal,
  onPending: () => void,
) => Promise<T>

function bffPath(path: string) {
  const url = new URL(path, window.location.origin)
  if (
    url.origin !== window.location.origin ||
    !url.pathname.startsWith(prefix + '/') ||
    url.username ||
    url.password ||
    url.hash
  ) {
    throw new BffError('INVALID_BFF_URL', 0, false)
  }
  return url.pathname + url.search
}

function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    signal.throwIfAborted()
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, ms)
    function abort() {
      clearTimeout(timer)
      reject(signal.reason)
    }
    signal.addEventListener('abort', abort, { once: true })
  })
}

export function createBffClient(
  fetcher: typeof fetch = (...args) => fetch(...args),
) {
  async function request(
    path: string,
    signal: AbortSignal,
    init?: RequestInit,
  ) {
    const url = bffPath(path)
    let response: Response
    try {
      response = await fetcher(url, {
        ...init,
        credentials: 'include',
        redirect: 'error',
        cache: 'no-store',
        signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
      })
    } catch {
      signal.throwIfAborted()
      throw new BffError('NETWORK_ERROR')
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new BffError(
        typeof body?.code === 'string' ? body.code : 'HTTP_ERROR',
        response.status,
      )
    }
    return response
  }

  async function json<T>(response: Response): Promise<T> {
    try {
      return (await response.json()) as T
    } catch {
      throw new BffError('INVALID_RESPONSE')
    }
  }

  const get = async <T>(path: string, signal: AbortSignal) =>
    json<T>(await request(prefix + path, signal))

  function post(path: string, body?: object, key?: string) {
    return {
      path: prefix + path,
      init: {
        method: 'POST',
        headers: {
          'X-Portal-Request': '1',
          ...(body && { 'Content-Type': 'application/json' }),
          ...(key && { 'Idempotency-Key': key }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      },
    }
  }

  function command(path: string, body?: object): Command<Operation> {
    const { path: url, init } = post(path, body, crypto.randomUUID())
    let accepted: { receipt: Receipt; delay: number } | undefined
    return async (signal, onPending) => {
      if (!accepted) {
        const response = await request(url, signal, init)
        if (response.status !== 202) throw new BffError('INVALID_RESPONSE')
        const receipt = await json<Receipt>(response)
        const retryAfter = Number(response.headers.get('Retry-After'))
        accepted = { receipt, delay: retryAfter > 0 ? retryAfter * 1000 : 0 }
      }

      const { receipt } = accepted
      let { delay } = accepted
      const statusUrl = bffPath(receipt.status_url)
      if (!statusUrl.startsWith(prefix + '/operations/')) {
        throw new BffError('INVALID_BFF_URL', 0, false)
      }
      onPending()
      for (let attempt = 0; attempt < 30; attempt += 1) {
        if (delay) await wait(Math.min(delay, 15_000), signal)
        const operation = await json<Operation>(
          await request(statusUrl, signal),
        )
        if (operation.operation_id !== receipt.operation_id)
          throw new BffError('INVALID_RESPONSE')
        switch (operation.state) {
          case 'succeeded':
            return operation
          case 'failed':
          case 'rejected':
            throw new BffError(
              operation.error?.code ?? 'COMMAND_FAILED',
              0,
              false,
            )
          case 'pending':
          case 'processing':
            delay = Math.max(1000, delay)
            break
          default:
            throw new BffError('INVALID_RESPONSE')
        }
      }
      throw new BffError('OPERATION_TIMEOUT')
    }
  }

  function ensureSession(): Command<Principal> {
    const { path, init } = post(
      '/auth/guest-sessions',
      undefined,
      crypto.randomUUID(),
    )
    return async (signal) => {
      try {
        return await get<Principal>('/auth/session', signal)
      } catch (error) {
        if (!(error instanceof BffError) || error.code !== 'SESSION_REQUIRED')
          throw error
        return json<Principal>(await request(path, signal, init))
      }
    }
  }

  return {
    ensureSession,
    survey: (
      signal: AbortSignal,
      id = 'rheuma_screening_v1',
      weights?: string,
    ) =>
      get<Survey>(
        '/surveys/' +
          segment(id) +
          (weights === undefined ? '' : '?weights_version=' + segment(weights)),
        signal,
      ),
    screening: (id: string, signal: AbortSignal) =>
      get<Screening>(screeningPath(id), signal),
    start: (body: Start) => command('/screenings', body),
    answer: (id: string, body: Answer) =>
      command(screeningPath(id) + '/answers', body),
    continueScreening: (id: string, body: Revision) =>
      command(screeningPath(id) + '/continuations', body),
    complete: (id: string, body: Revision) =>
      command(screeningPath(id) + '/completions', body),
    result: (ref: ResultRef, signal: AbortSignal) =>
      get<Result>(resultPath(ref), signal),
    explanation: (ref: ResultRef, signal: AbortSignal) =>
      get<Explanation>(resultPath(ref) + '/explanation', signal),
    requestExplanation: (ref: ResultRef) =>
      command(resultPath(ref) + '/explanation'),
    articles: (offset: number, signal: AbortSignal) =>
      get<ArticlePage>('/knowledge-base/articles?offset=' + offset, signal),
    article: (slug: string, signal: AbortSignal) =>
      get<Article>('/knowledge-base/articles/' + segment(slug), signal),
    doctorRoute: (signal: AbortSignal) =>
      get<Material>('/doctor-route', signal),
  }
}

export const bff = createBffClient()
