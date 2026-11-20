import './about.css'
import { policyHref } from '@entities'
import { t } from '@shared/i18n'

const operatorFields = [
  'fullName',
  'shortName',
  'taxId',
  'registrationId',
  'address',
  'postalAddress',
  'domain',
  'email',
  'privacyEmail',
  'phone',
] as const

function OperatorDetails() {
  return (
    <section>
      <h2>{t('about.details.title')}</h2>
      <dl className="operator-details">
        {operatorFields.map((field) => (
          <div key={field}>
            <dt>{t(`about.details.${field}`)}</dt>
            <dd>{t(`about.details.${field}Placeholder`)}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function LegalReferences() {
  return (
    <section>
      <h2>{t('about.laws.title')}</h2>
      <ul>
        <li>
          <a href="https://www.consultant.ru/document/cons_doc_LAW_61798/546dcc703c0a1e08647b40a2eeaf9461168c7cb1/">
            {t('about.laws.information')}
          </a>
        </li>
        <li>
          <a href="https://www.consultant.ru/document/cons_doc_LAW_61801/">
            {t('about.laws.personalData')}
          </a>
        </li>
      </ul>
    </section>
  )
}

export default function AboutPage() {
  return (
    <article className="article">
      <h1>{t('about.title')}</h1>
      <p className="article__lead">{t('about.lead')}</p>
      <p className="article__meta">
        {t('about.revisionLabel')}{' '}
        <time dateTime="2026-11-13">{t('about.revisionDate')}</time>
        {' · '}
        {t('about.effectiveDate')}
      </p>

      <OperatorDetails />

      <section>
        <h2>{t('about.processing.title')}</h2>
        <p>{t('about.processing.requests')}</p>
        <p>{t('about.processing.contact')}</p>
      </section>

      <section>
        <h2>{t('about.notification.title')}</h2>
        <p>{t('about.notification.body')}</p>
      </section>

      <section>
        <h2>{t('about.limitations.title')}</h2>
        <p>
          {t('about.limitations.body')}{' '}
          <a href={policyHref('medical-advices')}>
            {t('about.limitations.link')}
          </a>
          .
        </p>
      </section>

      <LegalReferences />
    </article>
  )
}
