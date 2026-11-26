import { useCallback, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { bff, BffError, type Command } from '@shared/api/client'
import type {
  AnswerValue,
  Operation,
  Question,
  Screening,
  Survey,
} from '@shared/api/contracts'
import { useBffCommand, useBffQuery } from '@shared/api/useBff'
import { t } from '@shared/i18n'
import { RequestStatus } from '@shared/ui/RequestStatus'
import { resultRoute } from '@shared/routes'

export function ScreeningPage() {
  const { state, reload } = useBffQuery(bff.survey)
  return (
    <section className="article portal-flow">
      <h1>{t('nav.screening')}</h1>
      {state.status === 'success' ? (
        <StartScreening
          key={state.data.disclaimer_version + ':' + state.data.weights_version}
          survey={state.data}
          reload={reload}
        />
      ) : (
        <RequestStatus {...state} onRetry={reload} />
      )}
    </section>
  )
}

function StartScreening({
  survey,
  reload,
}: {
  survey: Survey
  reload: () => void
}) {
  const [accepted, setAccepted] = useState(false)
  const command = useBffCommand<void>()
  const navigate = useNavigate()

  function start() {
    const ensureSession = bff.ensureSession()
    const submit = bff.start({
      survey_id: survey.survey_id,
      weights_version: survey.weights_version,
      disclaimer_version: survey.disclaimer_version,
      disclaimer_accepted: true,
    })
    let sessionReady = false
    void command.run(async (signal, pending) => {
      if (!sessionReady) {
        await ensureSession(signal, pending)
        sessionReady = true
      }
      const operation = await submit(signal, pending)
      const screening = operation.resources.find(
        ({ resource_type }) => resource_type === 'screening',
      )
      if (!screening) throw new BffError('INVALID_RESPONSE')
      navigate('/screening/' + encodeURIComponent(screening.resource_id))
    })
  }

  return (
    <>
      <p>{survey.disclaimer}</p>
      {survey.thresholds_status === 'draft' && <p>{t('screening.draft')}</p>}
      <label>
        <input
          type="checkbox"
          checked={accepted}
          disabled={command.busy || command.retryable}
          onChange={(event) => setAccepted(event.target.checked)}
        />{' '}
        {survey.confirmation_text}
      </label>
      <div>
        <button
          type="button"
          disabled={
            !accepted || command.busy || command.state.status === 'error'
          }
          onClick={start}
        >
          {t('screening.start')}
        </button>
      </div>
      <RequestStatus
        {...command.state}
        onRetry={command.retryable ? command.retry : reload}
      />
    </>
  )
}

export function ScreeningSessionPage() {
  const { screeningId = '' } = useParams()
  return (
    <section className="article portal-flow">
      <h1>{t('nav.screening')}</h1>
      <ScreeningSession key={screeningId} id={screeningId} />
    </section>
  )
}

function ScreeningSession({ id }: { id: string }) {
  const load = useCallback(
    async (signal: AbortSignal) => {
      const session = await bff.screening(id, signal)
      const survey = await bff.survey(
        signal,
        session.survey_id,
        session.weights_version,
      )
      return { session, survey }
    },
    [id],
  )
  const { state, reload } = useBffQuery(load)
  if (state.status !== 'success')
    return <RequestStatus {...state} onRetry={reload} />
  return (
    <Questionnaire
      initial={state.data.session}
      survey={state.data.survey}
      reload={reload}
    />
  )
}

function Questionnaire({
  initial,
  survey,
  reload,
}: {
  initial: Screening
  survey: Survey
  reload: () => void
}) {
  const [session, setSession] = useState(initial)
  const command = useBffCommand<void>()
  const navigate = useNavigate()
  const answers = new Map(
    session.answers.map(({ question_code, value }) => [question_code, value]),
  )
  const revision = { expected_session_version: session.version }
  const locked = command.busy || command.state.status === 'error'

  function change(submit: Command<Operation>) {
    void command.run(async (signal, pending) => {
      await submit(signal, pending)
      const next = await bff.screening(session.screening_id, signal)
      setSession(next)
      if (next.status === 'completed' && next.result)
        navigate(resultRoute(next.result))
    })
  }

  return (
    <>
      {session.interrupted_by_red_flag && (
        <p role="alert">{survey.urgent_notice}</p>
      )}
      {session.result && (
        <Link to={resultRoute(session.result)}>
          {t('screening.viewResult')}
        </Link>
      )}
      {session.status === 'in_progress' ? (
        session.interrupted_by_red_flag ? (
          <div>
            <button
              type="button"
              disabled={locked}
              onClick={() =>
                change(bff.continueScreening(session.screening_id, revision))
              }
            >
              {t('screening.continue')}
            </button>
          </div>
        ) : (
          <>
            {survey.blocks.map((block) => (
              <div className="portal-flow" key={block.code}>
                <h2>{block.title}</h2>
                {block.questions.map((question) => (
                  <QuestionField
                    key={question.code}
                    question={question}
                    disabled={locked}
                    answer={answers.get(question.code)}
                    onAnswer={(value) =>
                      change(
                        bff.answer(session.screening_id, {
                          ...revision,
                          question_code: question.code,
                          value,
                        }),
                      )
                    }
                  />
                ))}
              </div>
            ))}
            <div>
              <button
                type="button"
                disabled={
                  locked ||
                  survey.blocks.some(({ questions }) =>
                    questions.some((q) => q.required && !answers.has(q.code)),
                  )
                }
                onClick={() =>
                  change(bff.complete(session.screening_id, revision))
                }
              >
                {t('screening.complete')}
              </button>
            </div>
          </>
        )
      ) : (
        <p>
          {t(
            session.status === 'completed'
              ? 'screening.completed'
              : 'screening.abandoned',
          )}
        </p>
      )}
      <RequestStatus
        {...command.state}
        onRetry={command.retryable ? command.retry : reload}
      />
      {command.state.status === 'success' && (
        <p role="status">{t('screening.saved')}</p>
      )}
    </>
  )
}

function QuestionField({
  question,
  answer,
  disabled,
  onAnswer,
}: {
  question: Question
  answer: AnswerValue | undefined
  disabled: boolean
  onAnswer: (value: AnswerValue) => void
}) {
  const options =
    question.type === 'boolean'
      ? [
          { value: true, label: t('screening.yes') },
          { value: false, label: t('screening.no') },
        ]
      : question.options
  return (
    <fieldset disabled={disabled}>
      <legend>
        {question.text}
        {question.required && ' *'}
      </legend>
      {options.map(({ value, label }) => (
        <label key={String(value)}>
          <input
            type="radio"
            name={question.code}
            checked={answer === value}
            onChange={() => onAnswer(value)}
          />{' '}
          {label}
        </label>
      ))}
    </fieldset>
  )
}
