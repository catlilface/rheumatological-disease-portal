import './cookie-notice.css'
import { useEffect, useRef, useState } from 'react'

import {
  allAccepted,
  allRejected,
  optionalCookies,
  type CookieConsent,
} from '../model/consent'

type CookieNoticeProps = {
  consent: CookieConsent | null
  settingsOpen: boolean
  onOpenSettings: () => void
  onSave: (consent: CookieConsent) => void
}

export function CookieNotice({
  consent,
  settingsOpen,
  onOpenSettings,
  onSave,
}: CookieNoticeProps) {
  const [selection, setSelection] = useState(consent ?? allRejected)
  const settings = useRef<HTMLFieldSetElement>(null)

  useEffect(() => {
    if (settingsOpen) settings.current?.focus()
  }, [settingsOpen])

  return (
    <section className="cookie-notice" aria-labelledby="cookie-title">
      <div className="container cookie-notice__inner">
        <div>
          <h2 id="cookie-title">Использование cookie</h2>
          <p>
            Вы можете разрешить необязательные cookie или отключить их.{' '}
            <a href="/policy/cookies">Политика использования cookie (PDF)</a>
          </p>
        </div>
        <div className="cookie-notice__actions">
          <button type="button" onClick={() => onSave(allAccepted)}>
            Принять необязательные
          </button>
          <button type="button" onClick={() => onSave(allRejected)}>
            Отклонить необязательные
          </button>
          {settingsOpen ? null : (
            <button type="button" onClick={onOpenSettings}>
              Настроить
            </button>
          )}
        </div>
        {settingsOpen && (
          <fieldset
            className="cookie-notice__settings"
            ref={settings}
            tabIndex={-1}
          >
            <legend>Необязательные cookie</legend>
            {optionalCookies.map(({ id, label, description }) => (
              <label key={id}>
                <input
                  type="checkbox"
                  checked={selection[id]}
                  onChange={(event) =>
                    setSelection({ ...selection, [id]: event.target.checked })
                  }
                />
                <span>
                  <strong>{label}</strong>
                  <br />
                  {description}
                </span>
              </label>
            ))}
            <button type="button" onClick={() => onSave(selection)}>
              Сохранить настройки
            </button>
          </fieldset>
        )}
      </div>
    </section>
  )
}
