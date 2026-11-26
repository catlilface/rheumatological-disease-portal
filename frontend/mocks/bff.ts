import type {
  Answer,
  Explanation,
  Operation,
  Principal,
  Result,
  Screening,
  Start,
} from '../src/shared/api/contracts.ts'
import { article, doctorRoute, survey } from './fixtures.ts'

const prefix = '/api/v1'
const randomUUID = () => crypto.randomUUID()
const uuid = /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i
const json = (data: unknown, status = 200, headers?: Record<string, string>) =>
  Response.json(data, {
    status,
    headers: { 'Cache-Control': 'no-store', ...headers },
  })
const error = (status: number, code: string) =>
  json({ code, message: code, request_id: randomUUID() }, status)
const resultKey = ({
  result_id,
  version,
}: {
  result_id: string
  version: number
}) => result_id + '/' + version
const disclaimer = {
  disclaimer: survey.disclaimer,
  disclaimer_version: survey.disclaimer_version,
}

type Intent = {
  methodAndBody: string
  operation: Operation
  remainingPolls: number
}

export function createMockBff({ pendingPolls = 1 } = {}) {
  const guests = new Map<string, string>()
  type Session = {
    screenings: Map<string, Screening>
    results: Map<string, Result>
    explanations: Map<string, Explanation>
    intents: Map<string, Intent>
    operations: Map<string, Intent>
  }
  const sessions = new Map<string, Session>()

  function guest(token: string) {
    return json(
      {
        kind: 'guest',
        roles: [],
        session_expires_at: new Date(Date.now() + 3600_000).toISOString(),
      } satisfies Principal,
      201,
      {
        'Set-Cookie':
          'portal_session=' + token + '; HttpOnly; SameSite=Lax; Path=/',
      },
    )
  }

  function accept(
    session: Session,
    key: string,
    path: string,
    body: string,
    execute: () => Operation['resources'] | string,
  ) {
    const methodAndBody = path + '\n' + body
    let intent = session.intents.get(key)
    if (intent && intent.methodAndBody !== methodAndBody) {
      return error(409, 'IDEMPOTENCY_KEY_REUSED')
    }
    if (!intent) {
      const outcome = execute()
      const operation: Operation = {
        operation_id: randomUUID(),
        updated_at: new Date().toISOString(),
        ...(typeof outcome === 'string'
          ? {
              state: 'rejected',
              resources: [],
              error: { code: outcome, message: outcome },
            }
          : { state: 'succeeded', resources: outcome }),
      }
      intent = { operation, methodAndBody, remainingPolls: pendingPolls }
      session.intents.set(key, intent)
      session.operations.set(operation.operation_id, intent)
    }
    const status_url =
      prefix + '/operations/screening/' + intent.operation.operation_id
    return json(
      { operation_id: intent.operation.operation_id, status_url },
      202,
      { Location: status_url },
    )
  }

  return async function handle(request: Request): Promise<Response> {
    const url = new URL(request.url)
    const path = url.pathname.slice(prefix.length)
    const { method, headers } = request
    const cookie = headers
      .get('Cookie')
      ?.match(/(?:^|;\s*)portal_session=([^;]+)/)?.[1]
    const session = cookie ? sessions.get(cookie) : undefined
    const key = headers.get('Idempotency-Key') ?? ''
    if (method === 'POST' && headers.get('X-Portal-Request') !== '1')
      return error(403, 'BROWSER_REQUEST_DENIED')
    if (method === 'POST' && !uuid.test(key))
      return error(422, 'VALIDATION_ERROR')

    if (method === 'GET') {
      if (
        path === '/surveys/' + survey.survey_id &&
        (!url.searchParams.has('weights_version') ||
          url.searchParams.get('weights_version') === survey.weights_version)
      )
        return json(survey)
      if (path === '/doctor-route') return json(doctorRoute)
      if (path === '/knowledge-base/articles/' + article.slug)
        return json(article)
      if (path === '/knowledge-base/articles') {
        const offset = Number(url.searchParams.get('offset') ?? '0')
        if (!Number.isSafeInteger(offset) || offset < 0)
          return error(422, 'VALIDATION_ERROR')
        return json({
          items: offset === 0 ? [article] : [],
          total: 1,
          offset,
          limit: 20,
        })
      }
    }

    if (method === 'POST' && path === '/auth/guest-sessions') {
      const existing = guests.get(key)
      if (existing)
        return existing === cookie
          ? guest(existing)
          : error(409, 'GUEST_SESSION_ALREADY_ISSUED')
      const token = randomUUID()
      guests.set(key, token)
      sessions.set(token, {
        screenings: new Map(),
        results: new Map(),
        explanations: new Map(),
        intents: new Map(),
        operations: new Map(),
      })
      return guest(token)
    }

    if (!session) return error(401, 'SESSION_REQUIRED')
    const [, group, id, action, version, detail] = path.split('/')
    if (method === 'GET') {
      if (path === '/auth/session') {
        return json({
          kind: 'guest',
          roles: [],
          session_expires_at: new Date(Date.now() + 3600_000).toISOString(),
        } satisfies Principal)
      }
      if (group === 'operations' && id === 'screening') {
        const intent = session.operations.get(action)
        if (!intent) return error(404, 'NOT_FOUND')
        if (intent.remainingPolls > 0) {
          intent.remainingPolls -= 1
          return json({
            ...intent.operation,
            state: 'pending',
            resources: [],
            error: undefined,
          })
        }
        return json(intent.operation)
      }
      if (group === 'screenings' && !action) {
        const screening = session.screenings.get(id)
        return screening ? json(screening) : error(404, 'NOT_FOUND')
      }
      if (group === 'results' && action === 'versions') {
        const ref = id + '/' + version
        const result = session.results.get(ref)
        if (!result) return error(404, 'NOT_FOUND')
        if (!detail) return json(result)
        if (detail === 'explanation') {
          const explanation = session.explanations.get(ref)
          return explanation
            ? json(explanation)
            : error(404, 'EXPLANATION_NOT_READY')
        }
      }
    }
    if (method !== 'POST') return error(404, 'NOT_FOUND')
    const raw = await request.text()
    let body
    try {
      body = raw ? JSON.parse(raw) : null
    } catch {
      return error(400, 'INVALID_JSON')
    }

    if (path === '/screenings') {
      const start: Start = body
      if (start?.disclaimer_accepted !== true)
        return error(422, 'VALIDATION_ERROR')
      return accept(session, key, path, raw, () => {
        if (
          start.survey_id !== survey.survey_id ||
          start.weights_version !== survey.weights_version
        )
          return 'SURVEY_NOT_FOUND'
        if (start.disclaimer_version !== survey.disclaimer_version)
          return 'DISCLAIMER_VERSION_MISMATCH'
        const screening_id = randomUUID()
        session.screenings.set(screening_id, {
          ...disclaimer,
          screening_id,
          survey_id: survey.survey_id,
          weights_version: survey.weights_version,
          version: 1,
          status: 'in_progress',
          interrupted_by_red_flag: false,
          answers: [],
          result: null,
        })
        return [
          { resource_type: 'screening', resource_id: screening_id, version: 1 },
        ]
      })
    }

    if (
      group === 'screenings' &&
      ['answers', 'completions', 'continuations'].includes(action)
    ) {
      if (
        !Number.isSafeInteger(body?.expected_session_version) ||
        body.expected_session_version < 1
      ) {
        return error(422, 'VALIDATION_ERROR')
      }
      return accept(session, key, path, raw, () => {
        const screening = session.screenings.get(id)
        if (!screening) return 'NOT_FOUND'
        if (screening.status !== 'in_progress') return 'SESSION_CLOSED'
        if (screening.version !== body.expected_session_version)
          return 'SESSION_VERSION_CONFLICT'
        const questions = survey.blocks.flatMap(({ questions }) => questions)
        if (action === 'continuations') {
          if (!screening.interrupted_by_red_flag) return 'NOT_INTERRUPTED'
          screening.interrupted_by_red_flag = false
        } else if (action === 'answers') {
          if (screening.interrupted_by_red_flag) return 'CONTINUATION_REQUIRED'
          const { question_code, value }: Answer = body
          const question = questions.find(({ code }) => code === question_code)
          if (!question) return 'NOT_FOUND'
          if (
            question.type === 'boolean'
              ? typeof value !== 'boolean'
              : !question.options.some((option) => option.value === value)
          )
            return 'INVALID_ANSWER'
          screening.answers = [
            ...screening.answers.filter(
              (answer) => answer.question_code !== question_code,
            ),
            { question_code, value },
          ]
          if (question.red_flag && value === true && !screening.result)
            screening.interrupted_by_red_flag = true
        } else {
          if (
            !questions.every(
              (question) =>
                !question.required ||
                screening.answers.some(
                  (answer) => answer.question_code === question.code,
                ),
            )
          )
            return 'REQUIRED_ANSWERS_MISSING'
          screening.status = 'completed'
        }

        screening.version += 1
        const refs = [
          {
            resource_type: 'screening',
            resource_id: id,
            version: screening.version,
          },
        ]
        if (
          action === 'completions' ||
          (action === 'answers' &&
            (screening.interrupted_by_red_flag || screening.result))
        ) {
          const ref = {
            result_id: screening.result?.result_id ?? randomUUID(),
            version: (screening.result?.version ?? 0) + 1,
          }
          const red_flag =
            screening.interrupted_by_red_flag || screening.result !== null
          session.results.set(resultKey(ref), {
            ...disclaimer,
            ...ref,
            screening_id: id,
            survey_id: survey.survey_id,
            weights_version: survey.weights_version,
            thresholds_status: 'draft',
            risk_level: red_flag ? 'red_flag' : 'low',
            red_flag,
            red_flag_codes: red_flag ? ['D1'] : [],
            score: red_flag ? null : 0,
            scoring_complete: !red_flag,
            block_scores: {},
            contributing_answers: [],
            recommendations: [
              { code: 'demo', text: 'Демонстрационный результат.' },
            ],
          })
          screening.result = ref
          refs.push({
            resource_type: 'result',
            resource_id: ref.result_id,
            version: ref.version,
          })
        }
        return refs
      })
    }
    if (
      group === 'results' &&
      action === 'versions' &&
      detail === 'explanation'
    ) {
      return accept(session, key, path, raw, () => {
        const ref = id + '/' + version
        if (!session.results.has(ref)) return 'NOT_FOUND'
        const result = { result_id: id, version: Number(version) }
        session.explanations.set(ref, {
          result,
          mode: 'curated_fallback',
          explanation: 'Демонстрационное пояснение.',
          questions_for_doctor: ['Что обсудить на приёме?'],
          disclaimer: survey.disclaimer,
          sources: [{ slug: article.slug, version: article.version }],
        })
        return [
          {
            resource_type: 'result',
            resource_id: id,
            version: Number(version),
          },
        ]
      })
    }
    return error(404, 'NOT_FOUND')
  }
}
