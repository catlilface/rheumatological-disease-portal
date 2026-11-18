import './footer.css'
import { useRef, useState } from 'react'
import {
  CookieNotice,
  readCookieConsent,
  saveCookieConsent,
} from '../../../features/cookie-consent'
import { ThemeSwitch } from '../../../features/theme-switch'

export default function SiteFooter() {
  const [consent, setConsent] = useState(readCookieConsent)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const cookieSettingsButton = useRef<HTMLButtonElement>(null)
  return (
    <>
      <footer className="footer">
        <div className="container footer__inner">
          <div>
            <h2>Медицинский дисклеймер</h2>
            <p>
              Информация на сайте носит справочный характер, не является
              диагнозом или клинической рекомендацией и не заменяет консультацию
              врача.
            </p>
            <a href="/policy/medical-advices">Полный текст дисклеймера (PDF)</a>
          </div>
          <nav className="footer__nav" aria-label="Информация о портале">
            <a href="/documents">Документы портала</a>
            <a href="/about">Сведения об операторе</a>
            <ThemeSwitch remember={consent?.functional === true} />
            <button
              type="button"
              className="text-button"
              ref={cookieSettingsButton}
              onClick={() => setSettingsOpen(true)}
            >
              Настройки cookie
            </button>
          </nav>
        </div>
      </footer>

      {(!consent || settingsOpen) && (
        <CookieNotice
          consent={consent}
          settingsOpen={settingsOpen}
          onOpenSettings={() => setSettingsOpen(true)}
          onSave={(choice) => {
            saveCookieConsent(choice)
            setConsent(choice)
            setSettingsOpen(false)
            cookieSettingsButton.current?.focus()
          }}
        />
      )}
    </>
  )
}
