import './cookie-notice.css'
import { policyHref } from '@entities'
import { t } from '@shared/i18n'
import { allAccepted, allRejected, type CookieConsent } from '../model/consent'
import { CookieSettings } from './CookieSettings'

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
  return (
    <section className="cookie-notice" aria-labelledby="cookie-title">
      <div className="container cookie-notice__inner">
        <div>
          <h2 id="cookie-title">{t('cookies.title')}</h2>
          <p>
            {t('cookies.intro')}{' '}
            <a href={policyHref('cookies')}>
              {t('policy.pdfLink', { title: t('policy.cookies.title') })}
            </a>
          </p>
        </div>
        <div className="cookie-notice__actions">
          <button type="button" onClick={() => onSave(allAccepted)}>
            {t('cookies.accept')}
          </button>
          <button type="button" onClick={() => onSave(allRejected)}>
            {t('cookies.reject')}
          </button>
          {!settingsOpen && (
            <button type="button" onClick={onOpenSettings}>
              {t('cookies.configure')}
            </button>
          )}
        </div>
        {settingsOpen && (
          <CookieSettings
            initialConsent={consent ?? allRejected}
            onSave={onSave}
          />
        )}
      </div>
    </section>
  )
}
