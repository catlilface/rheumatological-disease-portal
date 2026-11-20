import './documents.css'
import { Link } from 'react-router'
import { policyLinks } from '@entities'
import { t } from '@shared/i18n'

function PolicyItem({
  href,
  title,
  description,
}: (typeof policyLinks)[number]) {
  return (
    <li>
      <div>
        <a href={href}>{t(title)}</a>
        <p>{t(description)}</p>
      </div>
      <span>{t('documents.pdf')}</span>
    </li>
  )
}

export default function DocumentsPage() {
  return (
    <article className="article">
      <h1>{t('documents.title')}</h1>
      <ul className="document-list">
        {policyLinks.map((policy) => (
          <PolicyItem key={policy.href} {...policy} />
        ))}
        <li>
          <div>
            <Link to="/about">{t('about.operatorLink')}</Link>
            <p>{t('documents.operatorDescription')}</p>
          </div>
        </li>
      </ul>
    </article>
  )
}
