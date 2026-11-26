import { useCallback } from 'react'
import { Link, useParams } from 'react-router'
import { bff, BffError } from '@shared/api/client'
import type { Explanation, Result, ResultRef } from '@shared/api/contracts'
import { useBffCommand, useBffQuery } from '@shared/api/useBff'
import { t } from '@shared/i18n'
import { RequestStatus } from '@shared/ui/RequestStatus'

export function ResultPage() {
  const { resultId = '', version = '' } = useParams()
  return (
    <section className="article portal-flow">
      <h1>{t('result.title')}</h1>
      <ResultContent
        key={resultId + ':' + version}
        id={resultId}
        version={version}
      />
    </section>
  )
}

const riskLabels = {
  low: 'result.low',
  medium: 'result.medium',
  high: 'result.high',
  red_flag: 'result.redFlag',
} as const

function ResultContent({ id, version }: { id: string; version: string }) {
  const load = useCallback(
    (signal: AbortSignal) =>
      bff.result({ result_id: id, version: Number(version) }, signal),
    [id, version],
  )
  const { state, reload } = useBffQuery(load)
  if (state.status !== 'success')
    return <RequestStatus {...state} onRetry={reload} />
  const result: Result = state.data
  return (
    <>
      {result.thresholds_status === 'draft' && <p>{t('screening.draft')}</p>}
      <p>{t(riskLabels[result.risk_level])}</p>
      <p>{result.disclaimer}</p>
      <p>{t('result.version', { version: String(result.version) })}</p>
      {result.scoring_complete && result.score !== null && (
        <p>{t('result.score', { score: String(result.score) })}</p>
      )}
      <ul>
        {result.recommendations.map(({ code, text }) => (
          <li key={code}>{text}</li>
        ))}
      </ul>
      <Link to="/doctor">{t('nav.doctor')}</Link>
      <ResultExplanation result={result} />
    </>
  )
}

function ResultExplanation({ result }: { result: ResultRef }) {
  const { result_id, version } = result
  const command = useBffCommand<Explanation>()

  function explain() {
    const ref = { result_id, version }
    const submit = bff.requestExplanation(ref)
    void command.run(async (signal, pending) => {
      try {
        return await bff.explanation(ref, signal)
      } catch (error) {
        if (
          !(error instanceof BffError) ||
          error.code !== 'EXPLANATION_NOT_READY'
        )
          throw error
      }
      await submit(signal, pending)
      return bff.explanation(ref, signal)
    })
  }

  const saved =
    command.state.status === 'success' ? command.state.data : undefined
  return (
    <div className="portal-flow">
      <h2>{t('result.explanation')}</h2>
      {saved ? (
        <>
          <p>{saved.explanation}</p>
          <p>{saved.disclaimer}</p>
          {saved.questions_for_doctor.length > 0 && (
            <ul>
              {saved.questions_for_doctor.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div>
          <button
            type="button"
            disabled={command.busy || command.retryable}
            onClick={explain}
          >
            {t('result.explain')}
          </button>
        </div>
      )}
      <RequestStatus
        {...command.state}
        onRetry={command.retryable ? command.retry : undefined}
      />
    </div>
  )
}
