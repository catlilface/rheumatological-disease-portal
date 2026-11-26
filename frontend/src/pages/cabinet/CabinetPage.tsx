import { useState, useCallback } from 'react'
import { Link } from 'react-router'
import { bff, BffError, type Command } from '@shared/api/client'
import { useBffCommand, useBffQuery } from '@shared/api/useBff'
import { RequestStatus } from '@shared/ui/RequestStatus'
import { resultRoute } from '@shared/routes'
import { t } from '@shared/i18n'

function PatientData() {
  const profile = useBffQuery(bff.profile)
  const change = useBffCommand<void>()
  function save(task: Command<unknown>) {
    void change.run(async (signal, pending) => {
      await task(signal, pending)
      profile.reload()
    })
  }
  const reminders =
    profile.state.status === 'success'
      ? profile.state.data.reminders
      : undefined
  const [offset, setOffset] = useState(0)
  const history = useBffQuery(
    useCallback((signal: AbortSignal) => bff.history(offset, signal), [offset]),
  )
  const limit =
    history.state.status === 'success' ? history.state.data.limit : 20
  return (
    <>
      {profile.state.status === 'success' ? (
        <>
          <h2>{profile.state.data.name || t('cabinet.profile')}</h2>
          {profile.state.data.diagnosis && (
            <p>{profile.state.data.diagnosis}</p>
          )}
          {!profile.state.data.completed && reminders && (
            <form
              className="portal-flow"
              onSubmit={(e) => {
                e.preventDefault()
                const data = new FormData(e.currentTarget)
                save(
                  bff.finishProfile(
                    String(data.get('name')),
                    String(data.get('diagnosis')) || null,
                    reminders,
                  ),
                )
              }}
            >
              <label>
                {t('cabinet.name')}{' '}
                <input
                  name="name"
                  autoComplete="name"
                  maxLength={120}
                  required
                />
              </label>
              <label>
                {t('cabinet.diagnosis')}{' '}
                <input name="diagnosis" maxLength={500} />
              </label>
              <button disabled={change.busy}>{t('cabinet.save')}</button>
            </form>
          )}
          <h3>{t('cabinet.medications')}</h3>
          {profile.state.data.medications.length ? (
            <ul>
              {profile.state.data.medications.map((m) => (
                <li key={m.medication_id}>
                  {m.regimen.name} — {m.regimen.dose_text}
                </li>
              ))}
            </ul>
          ) : (
            <p>{t('cabinet.noMeds')}</p>
          )}
          <details>
            <summary>{t('cabinet.addMedication')}</summary>
            <form
              className="portal-flow"
              onSubmit={(e) => {
                e.preventDefault()
                const data = new FormData(e.currentTarget)
                save(
                  bff.addMedication(
                    String(data.get('name')),
                    String(data.get('dose')),
                    String(data.get('time')),
                    String(data.get('start')),
                  ),
                )
              }}
            >
              <label>
                {t('cabinet.drugName')}{' '}
                <input name="name" maxLength={200} required />
              </label>
              <label>
                {t('cabinet.dose')}{' '}
                <input name="dose" maxLength={200} required />
              </label>
              <label>
                {t('cabinet.time')} <input type="time" name="time" required />
              </label>
              <label>
                {t('cabinet.start')} <input type="date" name="start" required />
              </label>
              <button disabled={change.busy}>{t('cabinet.saveDrug')}</button>
            </form>
          </details>
          <RequestStatus
            {...change.state}
            onRetry={change.retryable ? change.retry : undefined}
          />
        </>
      ) : (
        <RequestStatus {...profile.state} onRetry={profile.reload} />
      )}
      <h2>{t('cabinet.history')}</h2>
      {history.state.status === 'success' ? (
        <>
          {history.state.data.total === 0 ? (
            <p>{t('cabinet.noResults')}</p>
          ) : (
            <ol start={offset + 1}>
              {history.state.data.items.map((r, i) => (
                <li key={resultRoute(r)}>
                  <Link to={resultRoute(r)}>
                    {t('cabinet.result', {
                      number: String(offset + i + 1),
                      version: String(r.version),
                    })}
                  </Link>
                </li>
              ))}
            </ol>
          )}
          {offset > 0 && (
            <button onClick={() => setOffset(Math.max(0, offset - limit))}>
              {t('library.previous')}
            </button>
          )}
          {offset + history.state.data.limit < history.state.data.total && (
            <button onClick={() => setOffset(offset + limit)}>
              {t('library.next')}
            </button>
          )}
        </>
      ) : (
        <RequestStatus {...history.state} onRetry={history.reload} />
      )}
    </>
  )
}

export function CabinetPage() {
  const session = useBffQuery(bff.principal)
  const action = useBffCommand<void>()
  const state = session.state
  const needsLogin =
    (state.status === 'success' && state.data.kind === 'guest') ||
    (state.status === 'error' &&
      state.error instanceof BffError &&
      state.error.code === 'SESSION_REQUIRED')
  return (
    <section className="article portal-flow">
      <h1>{t('nav.cabinet')}</h1>
      {needsLogin ? (
        <form
          className="portal-flow"
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            event.currentTarget.reset()
            void action.run(async (signal) => {
              await bff.signIn(
                String(data.get('email')),
                String(data.get('password')),
                signal,
              )
              session.reload()
            }, false)
          }}
        >
          <label>
            {t('cabinet.email')}{' '}
            <input name="email" type="email" autoComplete="username" required />
          </label>
          <label>
            {t('cabinet.password')}{' '}
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
            />
          </label>
          <button disabled={action.busy}>{t('cabinet.login')}</button>
        </form>
      ) : state.status === 'success' ? (
        <>
          {state.data.roles.includes('patient') ? (
            <PatientData />
          ) : (
            <p>{t('cabinet.patientOnly')}</p>
          )}
          <button
            disabled={action.busy}
            onClick={() =>
              void action.run(async (signal) => {
                await bff.signOut(signal)
                session.reload()
              })
            }
          >
            {t('cabinet.logout')}
          </button>
        </>
      ) : (
        <RequestStatus {...state} onRetry={session.reload} />
      )}
      <RequestStatus {...action.state} />
    </section>
  )
}
