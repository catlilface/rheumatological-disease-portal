import './footer.css'
import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { policyHref } from '@entities'
import {
  CookieNotice,
  readCookieConsent,
  saveCookieConsent,
  ThemeSwitch,
  useTheme,
  type CookieConsent,
} from '@features'
import { t } from '@shared/i18n'

function MedicalDisclaimer() {
  return (
    <div>
      <h2>{t('policy.medical-advices.title')}</h2>
      <p>{t('disclaimer.summary')}</p>
      <a href={policyHref('medical-advices')}>{t('disclaimer.fullText')}</a>
    </div>
  )
}

export default function SiteFooter() {
  const [consent, setConsent] = useState(readCookieConsent)
  const rememberTheme = consent?.functional === true
  const { theme, canChange, changeTheme, syncConsent } = useTheme(rememberTheme)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const cookieSettingsButton = useRef<HTMLButtonElement>(null)

  const openSettings = () => setSettingsOpen(true)
  const saveConsent = (choice: CookieConsent) => {
    saveCookieConsent(choice)
    if (choice.functional !== rememberTheme) syncConsent(choice.functional)
    setConsent(choice)
    setSettingsOpen(false)
    cookieSettingsButton.current?.focus()
  }

  return (
    <>
      <footer className="footer">
        <div className="container footer__inner">
          <MedicalDisclaimer />
          <nav className="footer__nav" aria-label={t('nav.footer')}>
            <Link to="/documents">{t('documents.title')}</Link>
            <Link to="/about">{t('about.operatorLink')}</Link>
            <ThemeSwitch
              theme={theme}
              canChange={canChange}
              onChange={changeTheme}
            />
            <button
              type="button"
              className="text-button"
              ref={cookieSettingsButton}
              onClick={openSettings}
            >
              {t('cookies.settings')}
            </button>
          </nav>
        </div>
      </footer>

      {(!consent || settingsOpen) && (
        <CookieNotice
          consent={consent}
          settingsOpen={settingsOpen}
          onOpenSettings={openSettings}
          onSave={saveConsent}
        />
      )}
    </>
  )
}
